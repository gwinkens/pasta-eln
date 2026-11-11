"""Tests for templates: export and import of item types and of single items"""
# pylint: disable=consider-using-with,invalid-name,missing-function-docstring
import json
import tempfile
import unittest
from pathlib import Path
from pasta_eln.backend_worker import templates
from pasta_eln.backend_worker.sqlite import SqlLiteDB

DEVICE_ID = 'd-'+'1'*32


def schemas(db:SqlLiteDB) -> dict[str, list[dict[str, str]]]:
  """Fields of all item types, as the item type editor sends them for the import preview"""
  return {docType: db.dataHierarchy(docType, 'meta') for docType in db.dataHierarchy('', '')}


class TestTemplates(unittest.TestCase):
  """Templates are exported from one project group and imported into another one"""

  def setUp(self) -> None:
    self.tempDir = tempfile.TemporaryDirectory()
    base = Path(self.tempDir.name)
    (base/'source').mkdir()
    (base/'target').mkdir()
    self.source = SqlLiteDB(basePath=base/'source')
    self.target = SqlLiteDB(basePath=base/'target')
    self.fileName = base/'template.json'
    # source: devices have a serial number and a group with unit; a new subtype of measurements
    cursor = self.source.cursor
    cursor.execute("INSERT INTO docTypeSchema VALUES ('device', '', 4, 'serial number', '', '', '')")
    cursor.execute("INSERT INTO docTypeSchema VALUES ('device', 'calibration', 0, 'max load', 'mN', 'T', '')")
    cursor.execute("INSERT INTO definitions VALUES ('calibration.max load', 'Maximum load', '')")
    cursor.execute("INSERT INTO docTypes VALUES ('measurement/indentation', '', 'Indentations', '', '', 'name,tags')")
    for idx, (group, name, unit, choices) in enumerate([('', 'name', '', ''), ('', 'tags', '', ''),
        ('', 'comment', '', ''), ('', 'sample', '', 'sample'), ('', 'tip', '', 'berkovich,cube corner'),
        ('csm', 'frequency', 'Hz', '')]):
      cursor.execute("INSERT INTO docTypeSchema VALUES ('measurement/indentation', ?, ?, ?, ?, '', ?)",
                     (group, str(idx), name, unit, choices))
    self.source.connection.commit()
    self.source.saveDoc({'id':DEVICE_ID, 'name':'MTS XP', 'type':['device'], 'tags':['_3','indenter'],
                         'comment':'Lab 2', 'user':'u', 'gui':[True,True], 'dateCreated':'x', 'dateModified':'x',
                         'branch':{'stack':[], 'child':0, 'path':None, 'show':[True], 'op':'c'},
                         '.vendor':'MTS', '.serial number':'A12', 'metaVendor':{'fileSize':'1'},
                         'calibration':{'max load':('500', 'mN', '', ''), 'linked sample':'s-'+'2'*32}})

  def tearDown(self) -> None:
    self.source.exit()
    self.target.exit()
    self.tempDir.cleanup()

  def test_itemTypes(self) -> None:
    template = templates.exportTemplate(self.source, ['device', 'measurement/indentation'])
    templates.writeTemplate(template, self.fileName)
    template = templates.readTemplate(self.fileName)
    device = template['itemTypes'][0]
    self.assertEqual(device['title'], 'Devices')
    self.assertIn({'group':'calibration', 'name':'max load', 'unit':'mN', 'mandatory':'T', 'list':'',
                   'description':'Maximum load', 'PURL':''}, device['fields'])
    # saving an item does not remove the description of its keys
    self.assertEqual([i['description'] for i in device['fields'] if i['name']=='vendor'], ['Who is the vendor?'])

    comparison = {i['docType']:i for i in templates.compareItemTypes(template, schemas(self.target))}
    self.assertEqual(comparison['device']['status'], 'different')
    self.assertEqual(comparison['device']['added'], ['serial number', 'calibration.max load'])
    self.assertEqual(comparison['device']['actions'][0], templates.ImportAction.MERGE)
    self.assertEqual(comparison['measurement/indentation']['status'], 'new')

    report = templates.importItemTypes(self.target, template, {'device':templates.ImportAction.MERGE,
                                                                    'measurement/indentation':templates.ImportAction.ADD})
    self.assertIn('Devices: 2 fields added', report)
    fields = [(i['class'], i['idx'], i['name'], i['unit']) for i in self.target.dataHierarchy('device', 'meta')]
    self.assertIn(('', '4', 'serial number', ''), fields)
    self.assertIn(('calibration', '0', 'max load', 'mN'), fields)
    self.assertEqual(self.target.dataHierarchy('measurement/indentation', 'title'), ('Indentations',))
    self.assertEqual(self.target.cursor.execute("SELECT long FROM definitions WHERE key='calibration.max load'")
                     .fetchone(), ('Maximum load',))
    self.assertEqual({i['status'] for i in templates.compareItemTypes(template, schemas(self.target))}, {'identical'})
    # adding again does not change an existing item type
    report = templates.importItemTypes(self.target, template, {'measurement/indentation':templates.ImportAction.ADD})
    self.assertIn('not imported', report)

  def test_replace(self) -> None:
    template = templates.exportTemplate(self.source, ['device'])
    device = template['itemTypes'][0]
    device['title'] = 'Instruments'
    device['fields'] = [i for i in device['fields'] if i['name']!='vendor']
    comparison = templates.compareItemTypes(template, schemas(self.target))[0]
    self.assertEqual(comparison['removed'], ['vendor'])
    templates.importItemTypes(self.target, template, {'device':templates.ImportAction.REPLACE})
    self.assertEqual(self.target.dataHierarchy('device', 'title'), ('Instruments',))
    self.assertNotIn('vendor', [i['name'] for i in self.target.dataHierarchy('device', 'meta')])

  def test_item(self) -> None:
    for withValues in (True, False):
      template = templates.exportTemplate(self.source, [], DEVICE_ID, withValues)
      self.assertEqual([i['docType'] for i in template['itemTypes']], ['device'])        # type is included
      item = template['items'][0]
      properties = {(i['group'], i['key']):(i['value'], i['unit']) for i in item['properties']}
      self.assertEqual(properties[('calibration', 'max load')], ('500' if withValues else '', 'mN'))
      self.assertEqual(properties[('calibration', 'linked sample')], ('', ''))   # links only exist in source
      self.assertNotIn(('metaVendor', 'fileSize'), properties)                     # belongs to the file
      self.assertEqual(item.get('tags'), ['indenter'] if withValues else None)     # without rating
      doc = templates.templateToDoc(item)
      self.assertEqual(doc['type'], ['device'])
      self.assertEqual(doc['calibration']['max load'], ('500' if withValues else '', 'mN', '', ''))
      self.assertEqual(doc.get('comment'), 'Lab 2' if withValues else None)

  def test_markdown(self) -> None:
    folder = Path(self.tempDir.name)
    item = {'docType':'workflow', 'name':'run 2026/11 x.md', 'properties':[], 'content':'# Run\n'+'step\n'*100}
    self.assertTrue(templates.isMarkdownItem(item))
    self.assertTrue(templates.isMarkdownItem(item | {'docType':'workflow/workplan'}))
    self.assertFalse(templates.isMarkdownItem(item | {'docType':'device'}))
    path = templates.writeMarkdown(item, folder)
    self.assertEqual(path.name, 'run_2026_11_x.md')
    self.assertEqual(path.read_text(encoding='utf-8'), item['content'])                  # complete content
    self.assertEqual(templates.writeMarkdown(item, folder).name, 'run_2026_11_x_1.md')  # existing file is kept
    self.assertEqual(path.read_text(encoding='utf-8'), item['content'])
    path = templates.writeMarkdown({'docType':'workflow', 'name':'', 'properties':[]}, folder)
    self.assertEqual((path.name, path.read_text(encoding='utf-8')), ('template.md', '# template\n'))

  def test_invalidFiles(self) -> None:
    for content, message in [('{', 'Cannot read'), ('{"format":"other"}', 'not a PASTA-ELN template'),
        (json.dumps({'format':templates.TEMPLATE_FORMAT, 'version':99}), 'newer version'),
        (json.dumps({'format':templates.TEMPLATE_FORMAT, 'version':1,
                     'itemTypes':[{'docType':'x0', 'title':'Projects', 'fields':[]}]}), 'invalid item type')]:
      self.fileName.write_text(content, encoding='utf-8')
      with self.assertRaisesRegex(ValueError, message):
        templates.readTemplate(self.fileName)


if __name__ == '__main__':
  unittest.main()
