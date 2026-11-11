""" Export and import of templates: item types (their fields) and single items (their key-value pairs)

A template file is JSON and can contain both:
- itemTypes: item types with their fields, as defined in the item type editor
- items: items with their key-value pairs, used to create new items. The item type of an item is also included,
  so that it can be imported into project groups that do not have it.

Workflow items are created as Markdown files, since the database only stores the beginning of the content.
"""
import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from .. import __version__
from ..misc_tools import isDocID
from .sqlite import SqlLiteDB

TEMPLATE_FORMAT  = 'PASTA-ELN template'
TEMPLATE_VERSION = 1
FIELD_KEYS       = ['group', 'name', 'unit', 'mandatory', 'list', 'description', 'PURL']    # per field of a type
SCHEMA_COMPARE   = ['unit', 'mandatory', 'list']                         # field properties compared during import
# groups of an item that are not part of a template: they belong to the specific file / measurement
SKIPPED_GROUPS   = ['metaVendor', 'metaUser']


class ImportAction(Enum):
  """ Import actions for item types; the value is the label shown to the user """
  SKIP    = 'Skip'
  ADD     = 'Add'
  MERGE   = 'Add missing fields'
  REPLACE = 'Replace'


def exportTemplate(db:SqlLiteDB, docTypes:list[str], docID:str='', withValues:bool=True) -> dict[str,Any]:
  """ Create a template of item types or of an item

  Args:
    db (SqlLiteDB): database
    docTypes (list): item types to export; ignored if docID is given
    docID (str): item to export; its item type is included
    withValues (bool): for an item: include values, comment, content and tags; otherwise only keys and units

  Returns:
    dict: template
  """
  template:dict[str,Any] = {'format':TEMPLATE_FORMAT, 'version':TEMPLATE_VERSION, 'pastaELN':__version__,
                            'exported':datetime.now().isoformat(timespec='seconds'), 'itemTypes':[], 'items':[]}
  if docID:
    doc = db.getDoc(docID)
    if not doc:
      raise ValueError(f'Item {docID} does not exist.')
    docTypes = ['/'.join(doc['type'])]
    template['items'].append(_itemTemplate(doc, withValues))
  for docType in docTypes:
    template['itemTypes'].append(_itemTypeTemplate(db, docType))
  return template


def _itemTypeTemplate(db:SqlLiteDB, docType:str) -> dict[str,Any]:
  """ Item type with its fields

  Args:
    db (SqlLiteDB): database
    docType (str): item type

  Returns:
    dict: item type template
  """
  db.cursor.execute('SELECT title, icon, shortcut, PURL, view FROM docTypes WHERE docType=?', (docType,))
  row = db.cursor.fetchone()
  if row is None:
    raise ValueError(f'Item type {docType} does not exist.')
  db.cursor.execute('SELECT key, long, PURL FROM definitions')
  definitions = {key:(long or '', purl or '') for key, long, purl in db.cursor.fetchall()}
  fields = []
  for field in sorted(db.dataHierarchy(docType, 'meta'), key=lambda i:(i['class'], int(i['idx']))):
    description, purl = definitions.get(f"{field['class']}.{field['name']}", ('', ''))
    fields.append({'group':field['class'], 'name':field['name'], 'unit':field['unit'] or '',
                   'mandatory':field['mandatory'] or '', 'list':field['list'] or '', 'description':description,
                   'PURL':purl})
  title, icon, shortcut, purl, view = (i or '' for i in row)
  return {'docType':docType, 'title':title, 'icon':icon, 'shortcut':shortcut, 'PURL':purl, 'view':view,
          'fields':fields}


def _itemTemplate(doc:dict[str,Any], withValues:bool) -> dict[str,Any]:
  """ Item with its key-value pairs

  Args:
    doc (dict): item as returned by the database
    withValues (bool): include values, comment, content and tags; otherwise only keys and units

  Returns:
    dict: item template
  """
  properties = []
  for group, content in doc.items():
    if not isinstance(content, dict) or group in SKIPPED_GROUPS or group in ['branch']:
      continue
    for key, value in content.items():
      if isinstance(value, tuple|list):
        value, unit = value[0], value[1]
      else:
        unit = ''
      value = '' if value is None else str(value)
      if not withValues or isDocID(value):                     # links to other items only exist in this database
        value = ''
      properties.append({'group':group, 'key':key, 'value':value, 'unit':unit or ''})
  item = {'docType':'/'.join(doc['type']), 'name':doc.get('name',''), 'properties':properties}
  if withValues:
    item |= {'comment':doc.get('comment',''), 'content':doc.get('content',''),
             'tags':[i for i in doc.get('tags',[]) if not i.startswith('_')]}               # without rating
  return item


def writeTemplate(template:dict[str,Any], fileName:str|Path) -> None:
  """ Write template to a JSON file

  Args:
    template (dict): template
    fileName (str, Path): file name
  """
  with open(fileName, 'w', encoding='utf-8') as fOut:
    json.dump(template, fOut, indent=2, ensure_ascii=False)


def readTemplate(fileName:str|Path) -> dict[str,Any]:
  """ Read and verify a template file

  Args:
    fileName (str, Path): file name

  Returns:
    dict: template

  Raises:
    ValueError: if the file is not a valid template
  """
  try:
    with open(fileName, encoding='utf-8') as fIn:
      template = json.load(fIn)
  except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
    raise ValueError(f'Cannot read template: {error}') from None
  if not isinstance(template, dict) or template.get('format')!=TEMPLATE_FORMAT:
    raise ValueError('This file is not a PASTA-ELN template.')
  if template.get('version', 0) > TEMPLATE_VERSION:
    raise ValueError('This template was created by a newer version of PASTA-ELN. Update PASTA-ELN to import it.')
  for itemType in template.get('itemTypes', []):
    if not itemType.get('docType') or not itemType.get('title') or not isinstance(itemType.get('fields'), list) or \
       any(not field.get('name') for field in itemType['fields']) or itemType['docType'].startswith('x'):
      raise ValueError('The template contains an invalid item type.')
  for item in template.get('items', []):
    if not item.get('docType') or not isinstance(item.get('properties', []), list):
      raise ValueError('The template contains an invalid item.')
  return template


def compareItemTypes(template:dict[str,Any], currentSchemas:dict[str,list[dict[str,Any]]]) -> list[dict[str,Any]]:
  """ Compare the item types of a template with those in the project group

  Args:
    template (dict): template
    currentSchemas (dict): docType: fields as in the docTypeSchema table (keys class, name, unit, mandatory, list)

  Returns:
    list: per item type of the template: docType, title, status ('new', 'identical', 'different'),
          added (fields only in template), removed (fields only in project group), changed (fields that differ)
          and the possible actions (first is the default)
  """
  result = []
  for itemType in template.get('itemTypes', []):
    entry:dict[str,Any] = {'docType':itemType['docType'], 'title':itemType['title'], 'added':[], 'removed':[],
                           'changed':[]}
    if itemType['docType'] not in currentSchemas:
      result.append(entry | {'status':'new', 'actions':[ImportAction.ADD, ImportAction.SKIP]})
      continue
    current = {(i['class'], i['name']):i for i in currentSchemas[itemType['docType']]}
    new     = {(i['group'], i['name']):i for i in itemType['fields']}
    entry['added']   = [_fieldLabel(key) for key in new if key not in current]
    entry['removed'] = [_fieldLabel(key) for key in current if key not in new]
    entry['changed'] = [_fieldLabel(key) for key in new if key in current and
                        any(str(new[key].get(i,'') or '')!=str(current[key].get(i,'') or '') for i in SCHEMA_COMPARE)]
    if entry['added'] or entry['removed'] or entry['changed']:
      actions = [ImportAction.MERGE, ImportAction.REPLACE, ImportAction.SKIP] if entry['added'] else \
                [ImportAction.SKIP, ImportAction.REPLACE]
      result.append(entry | {'status':'different', 'actions':actions})
    else:
      result.append(entry | {'status':'identical', 'actions':[ImportAction.SKIP]})
  return result


def _fieldLabel(key:tuple[str,str]) -> str:
  """ Field name shown to the user: group.name or name in the default group

  Args:
    key (tuple): group, name

  Returns:
    str: label
  """
  return f'{key[0]}.{key[1]}' if key[0] else key[1]


def importItemTypes(db:SqlLiteDB, template:dict[str,Any], actions:dict[str,ImportAction]) -> str:
  """ Import item types of a template into the project group

  Args:
    db (SqlLiteDB): database
    template (dict): template
    actions (dict): docType: ImportAction. Item types that are not listed are skipped.
      - ADD: create the item type (only if it does not exist)
      - MERGE: add the fields that the item type does not have; existing fields are not changed
      - REPLACE: replace the fields and the title, icon, ... of the item type

  Returns:
    str: report
  """
  report = []
  db.cursor.execute('SELECT docType FROM docTypes')
  existing = {i[0] for i in db.cursor.fetchall()}
  for itemType in template.get('itemTypes', []):
    docType = itemType['docType']
    action = actions.get(docType, ImportAction.SKIP)
    if action is ImportAction.SKIP:
      continue
    if action is ImportAction.ADD and docType in existing or \
       action in (ImportAction.MERGE, ImportAction.REPLACE) and docType not in existing:
      report.append(f'- {itemType["title"]}: not imported, since the item type '
                    f'{"exists" if action is ImportAction.ADD else "does not exist"}')
      continue
    fields = itemType['fields']
    nextIdx:dict[str,int] = {}                                                    # next free idx per group
    if action is ImportAction.MERGE:
      db.cursor.execute('SELECT class, name, idx FROM docTypeSchema WHERE docType=?', (docType,))
      current = db.cursor.fetchall()
      fields = [i for i in fields if (i['group'], i['name']) not in {(c, n) for c, n, _ in current}]
      for group, _, idx in current:
        nextIdx[group] = max(nextIdx.get(group, 0), int(idx)+1)
    else:
      if action is ImportAction.REPLACE:
        db.cursor.execute('DELETE FROM docTypeSchema WHERE docType=?', (docType,))
        db.cursor.execute('DELETE FROM docTypes WHERE docType=?', (docType,))
      db.cursor.execute('INSERT INTO docTypes (docType, PURL, title, icon, shortcut, view) VALUES (?, ?, ?, ?, ?, ?)',
                        (docType, itemType.get('PURL',''), itemType['title'], itemType.get('icon',''),
                         itemType.get('shortcut',''), itemType.get('view','')))
    for field in fields:
      idx = nextIdx.get(field['group'], 0)
      nextIdx[field['group']] = idx+1
      db.cursor.execute('INSERT INTO docTypeSchema (docType, class, idx, name, unit, mandatory, list) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?)', (docType, field['group'], str(idx), field['name'],
                        field.get('unit',''), field.get('mandatory',''), field.get('list','')))
      # descriptions are shared between item types: do not overwrite existing ones, except when replacing
      if field.get('description') or field.get('PURL'):
        conflict = 'UPDATE SET long=excluded.long, PURL=excluded.PURL' if action is ImportAction.REPLACE \
                   else 'NOTHING'
        db.cursor.execute(f'INSERT INTO definitions (key, long, PURL) VALUES (?, ?, ?) ON CONFLICT(key) DO {conflict}',
                          (f"{field['group']}.{field['name']}", field.get('description',''), field.get('PURL','')))
    missingLinks = {i['list'] for i in fields if i.get('list') and ',' not in i['list']}.difference(
                    existing | {i['docType'] for i in template.get('itemTypes', [])})
    text = {ImportAction.ADD:'added', ImportAction.MERGE:f'{len(fields)} fields added',
            ImportAction.REPLACE:'replaced'}[action]
    report.append(f'- {itemType["title"]}: {text}')
    if missingLinks:
      report.append(f'  - links to item types that do not exist: {", ".join(sorted(missingLinks))}')
  db.connection.commit()
  return '\n'.join(report) if report else 'Nothing imported.'


def isMarkdownItem(item:dict[str,Any]) -> bool:
  """ Items of the template that are created as Markdown file: all workflow items

  Args:
    item (dict): item of a template

  Returns:
    bool: True if the item is created as Markdown file
  """
  return item['docType'].split('/')[0] == 'workflow'


def writeMarkdown(item:dict[str,Any], folder:Path) -> Path:
  """ Write the content of an item of a template to a new Markdown file

  Args:
    item (dict): item of a template
    folder (Path): folder in which the file is created; existing files are not overwritten

  Returns:
    Path: the new file
  """
  stem = re.sub(r'[^\w.-]+', '_', item.get('name') or '').strip('_.') or 'template'
  stem = stem[:-3] if stem.lower().endswith('.md') else stem
  path, number = folder/f'{stem}.md', 1
  while path.exists():
    path, number = folder/f'{stem}_{number}.md', number+1
  content = item.get('content') or f"# {item.get('name') or stem}\n"
  with open(path, 'x', encoding='utf-8') as fOut:
    fOut.write(content)
  return path


def templateToDoc(item:dict[str,Any]) -> dict[str,Any]:
  """ Convert an item of a template into a document for the form that creates a new item

  Args:
    item (dict): item of a template

  Returns:
    dict: document with type, tags, comment, content and the key-value pairs as (value, unit, '', '') per group
  """
  doc:dict[str,Any] = {'type':item['docType'].split('/'), 'tags':list(item.get('tags', []))}
  for key in ('comment', 'content'):
    if item.get(key):
      doc[key] = item[key]
  for prop in item.get('properties', []):
    doc.setdefault(prop.get('group',''), {})[prop['key']] = (prop.get('value',''), prop.get('unit',''), '', '')
  return doc
