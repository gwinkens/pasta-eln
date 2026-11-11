"""GUI test of templates: export/import of item types in the item type editor, export of an item in the Details
and creation of a new item from a template in the table"""
# pylint: disable=invalid-name
import json
import logging
from PySide6.QtWidgets import QFileDialog, QMessageBox
from pasta_eln.backend_worker.templates import ImportAction
from pasta_eln.ui.data_hierarchy import editor as editorModule
from pasta_eln.ui.data_hierarchy.editor import Command as EditorCommand
from pasta_eln.ui.data_hierarchy.editor import SchemeEditor
from pasta_eln.ui.details.details import Command as DetailsCommand
from pasta_eln.ui.details.details import Details
from pasta_eln.ui.form.form import Command as FormCommand
from pasta_eln.ui.form.form import Form
from pasta_eln.ui.table.table import Command as TableCommand
from pasta_eln.ui.table.table import TableView
from pasta_eln.ui.gui_communicate import Communicate


def waitFor(qtbot, condition, timeout=20000):
  """Wait until condition() is true"""
  qtbot.waitUntil(condition, timeout=timeout)


def test_templates(qtbot, caplog, monkeypatch, tmp_path):
  comm = Communicate('research')
  while comm.backendThread.worker.backend is None or comm.backendThread.worker.backend.dbRaw is None:
    qtbot.wait(100)
  waitFor(qtbot, lambda: 'device' in comm.dataHierarchyNodes)
  db = comm.backendThread.worker.backend.db
  typesFile, itemFile = tmp_path/'types.json', tmp_path/'item.json'

  # item type editor: export devices
  editor = SchemeEditor(comm)
  qtbot.addWidget(editor)
  waitFor(qtbot, lambda: editor.tabW.count() > 1)                                     # fields are shown
  monkeypatch.setattr(editorModule.ItemTypeExportDialog, 'exec',
                      lambda self: setattr(self, 'selected', ['device']) or True)
  monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *_args, **_kwargs: (str(typesFile), ''))
  editor.execute(EditorCommand.EXPORT)
  waitFor(qtbot, typesFile.exists)
  template = json.loads(typesFile.read_text(encoding='utf-8'))
  assert [i['docType'] for i in template['itemTypes']] == ['device']

  # change the template: devices get a calibration group, and a new subtype of measurements
  template['itemTypes'][0]['fields'].append({'group':'calibration', 'name':'max load', 'unit':'mN', 'mandatory':'',
                                             'list':'', 'description':'Maximum load', 'PURL':''})
  template['itemTypes'].append({'docType':'measurement/indentation', 'title':'Indentations', 'icon':'',
                                'shortcut':'', 'PURL':'', 'view':'name,tags',
                                'fields':[{'group':'', 'name':'name', 'unit':'', 'mandatory':'T', 'list':''},
                                          {'group':'', 'name':'tip', 'unit':'', 'mandatory':'', 'list':''}]})
  typesFile.write_text(json.dumps(template), encoding='utf-8')

  # item type editor: import with preview; the default action of each item type is used
  previews = []
  def acceptPreview(self):
    previews.extend(self.comparison)
    self.importActions = {i['docType']:i['actions'][0] for i in self.comparison if i['actions'][0] is not ImportAction.SKIP}
    return True
  monkeypatch.setattr(editorModule.ItemTypeImportDialog, 'exec', acceptPreview)
  monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *_args, **_kwargs: (str(typesFile), ''))
  editor.execute(EditorCommand.IMPORT)
  waitFor(qtbot, lambda: 'measurement/indentation' in comm.dataHierarchyNodes)
  assert {i['docType']:i['status'] for i in previews} == {'device':'different', 'measurement/indentation':'new'}
  waitFor(qtbot, lambda: editor.selectDocType.findText('Indentations') >= 0)
  qtbot.wait(500)                               # editor reloads; it must not overwrite the imported fields
  assert ('calibration', 'max load', 'mN') in [(i['class'], i['name'], i['unit']) for i in db.dataHierarchy('device', 'meta')]
  editor.execute(EditorCommand.CANCEL)

  # Details: export a device with values as item template
  table = None
  def receiveTable(data, docType):
    nonlocal table
    if docType == 'device':
      table = data
  comm.backendThread.worker.beSendTable.connect(receiveTable)
  db.saveDoc({'id':'d-'+'7'*32, 'name':'MTS XP', 'type':['device'], 'tags':[], 'user':'u', 'gui':[True,True],
              'dateCreated':'x', 'dateModified':'x', 'comment':'Lab 2', '.vendor':'MTS',
              'branch':{'stack':[], 'child':0, 'path':None, 'show':[True], 'op':'c'},
              'calibration':{'max load':('500', 'mN', '', ''), 'temperature':('23', 'degC', '', '')},
              '.serial':('A12', '', '', '')})
  details = Details(comm)
  qtbot.addWidget(details)
  details.docID = 'd-'+'7'*32
  details.data = db.getDoc(details.docID)
  monkeypatch.setattr(QMessageBox, 'exec', lambda self: 0)
  monkeypatch.setattr(QMessageBox, 'clickedButton', lambda self: [i for i in self.buttons() if i.text()=='With values'][0])
  monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *_args, **_kwargs: (str(itemFile), ''))
  details.execute(DetailsCommand.EXPORT_TEMPLATE)
  waitFor(qtbot, itemFile.exists)
  item = json.loads(itemFile.read_text(encoding='utf-8'))['items'][0]
  assert {'group':'calibration', 'key':'max load', 'value':'500', 'unit':'mN'} in item['properties']

  # table: new item from the template; the form opens prefilled and the unit is kept when saving
  forms = []
  comm.formDoc.connect(forms.append)
  tableView = TableView(comm, 'device')
  qtbot.addWidget(tableView)
  monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *_args, **_kwargs: (str(itemFile), ''))
  tableView.execute(TableCommand.NEW_FROM_TEMPLATE)
  assert forms and forms[0]['calibration']['max load'] == ('500', 'mN', '', '')
  form = Form(comm, forms[0])
  qtbot.addWidget(form)
  form.key_0.setText('MTS XP copy')                                         # type: ignore[attr-defined]
  form.execute(FormCommand.FORM_SAVE)
  def newDoc():
    rows = db.cursor.execute("SELECT id FROM main WHERE name='MTS XP copy'").fetchall()
    return db.getDoc(rows[0][0]) if rows else None
  waitFor(qtbot, lambda: newDoc() is not None)
  doc = newDoc()
  assert doc['calibration']['max load'][:2] == ('500', 'mN')
  assert doc['calibration']['temperature'][:2] == ('23', 'degC')               # unit of a key not in the item type
  assert doc['']['serial'][0] == 'A12'
  assert doc['comment'] == 'Lab 2'

  # table: a workflow item is created as Markdown file in the project, with the complete content
  workflowFile = tmp_path/'workflow.json'
  content = '# Run\n\n' + '| parameter | value |\n'*50
  workflowFile.write_text(json.dumps({'format':'PASTA-ELN template', 'version':1, 'itemTypes':[],
                                      'items':[{'docType':'workflow', 'name':'run 1', 'properties':[],
                                                'comment':'from PYRAMID', 'content':content, 'tags':['PYRAMID']}]}),
                          encoding='utf-8')
  comm.projectID = db.cursor.execute("SELECT id FROM main WHERE type='x0'").fetchone()[0]
  forms.clear()
  tableView = TableView(comm, 'workflow')
  qtbot.addWidget(tableView)
  monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *_args, **_kwargs: (str(workflowFile), ''))
  reports = []
  comm.backendThread.worker.beSendTaskReport.connect(lambda task, text, *_args: reports.append(text))
  tableView.execute(TableCommand.NEW_FROM_TEMPLATE)
  def workflowDoc():
    rows = db.cursor.execute("SELECT id FROM main WHERE name='run_1.md'").fetchall()
    return db.getDoc(rows[0][0]) if rows else None
  waitFor(qtbot, lambda: workflowDoc() is not None)
  assert not forms                                                                         # no form opens
  doc = workflowDoc()
  path = comm.basePath/doc['branch'][0]['path']
  assert path.name == 'run_1.md' and path.parent == comm.basePath/db.getDoc(comm.projectID)['branch'][0]['path']
  assert path.read_text(encoding='utf-8') == content
  assert doc['type'][0] == 'workflow' and doc['comment'] == 'from PYRAMID' and 'PYRAMID' in doc['tags']
  waitFor(qtbot, lambda: bool(reports))
  assert reports[-1] == f"Created run_1.md from the template as {'/'.join(doc['type'])} item."
  comm.shutdownBackendThread()

  errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
  assert not errors, f'Logging errors found: {[record.getMessage() for record in errors]}'
