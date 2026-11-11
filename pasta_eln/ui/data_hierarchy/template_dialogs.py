""" Dialogs to export item types as template and to import them """
from enum import Enum
from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QHeaderView, QListWidget, QListWidgetItem,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)
from ...backend_worker.templates import ImportAction
from ..gui_communicate import Communicate
from ..gui_style import SPACE, Button, ButtonStyle, Label
from ..message_dialog import showMessage

STATUS = {'new':'New', 'identical':'Identical', 'different':'Different'}


class ItemTypeExportDialog(QDialog):
  """ Select the item types that are exported as template """
  def __init__(self, comm:Communicate, current:str=''):
    """
    Initialization

    Args:
      comm (Communicate): Shared communication object.
      current (str): item type that is selected at the start
    """
    super().__init__()
    self.comm = comm
    self.selected:list[str] = []
    self.setWindowTitle('Export item types')
    mainL = QVBoxLayout(self)
    mainL.setContentsMargins(SPACE.M, SPACE.M, SPACE.M, SPACE.M)
    mainL.setSpacing(SPACE.S)
    Label('Select the item types to export as template', 'h3', mainL)
    self.listW = QListWidget()
    for docType, info in comm.docTypesTitles.items():
      if docType.startswith('x'):                                                   # projects and folders
        continue
      item = QListWidgetItem(f"{info['title']} ({docType})")
      item.setData(Qt.ItemDataRole.UserRole, docType)
      item.setCheckState(Qt.CheckState.Checked if docType==current else Qt.CheckState.Unchecked)
      self.listW.addItem(item)
    mainL.addWidget(self.listW)
    footer = QHBoxLayout()
    footer.addStretch()
    Button('Cancel', self, Command.CANCEL, footer)
    Button('Export…', self, Command.OK, footer, style=ButtonStyle.HIGHLIGHTED)
    mainL.addLayout(footer)


  def execute(self, command:'Command') -> None:
    """ Event if user clicks button

    Args:
      command (Command): command
    """
    if command is Command.CANCEL:
      self.reject()
    elif command is Command.OK:
      self.selected = [self.listW.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.listW.count())
                       if self.listW.item(i).checkState()==Qt.CheckState.Checked]
      if not self.selected:
        showMessage(self, 'No item type selected', 'Select at least one item type.')
        return
      self.accept()


class ItemTypeImportDialog(QDialog):
  """ Preview of the item types of a template: what differs and what should be imported """
  def __init__(self, comm:Communicate, comparison:list[dict[str,Any]]):
    """
    Initialization

    Args:
      comm (Communicate): Shared communication object.
      comparison (list): result of compareItemTypes
    """
    super().__init__()
    self.comm = comm
    self.comparison = comparison
    self.importActions:dict[str,ImportAction] = {}                                       # docType: action
    self.setWindowTitle('Import item types')
    self.setMinimumWidth(800)
    mainL = QVBoxLayout(self)
    mainL.setContentsMargins(SPACE.M, SPACE.M, SPACE.M, SPACE.M)
    mainL.setSpacing(SPACE.S)
    Label('Select what to import for each item type', 'h3', mainL)
    explanation = Label('"Add missing fields" keeps all existing fields unchanged. "Replace" also removes fields that '
                        'are not in the template and replaces the name, icon and shortcut of the item type.', '', mainL)
    explanation.setWordWrap(True)
    self.table = QTableWidget(len(comparison), 4)
    self.table.setHorizontalHeaderLabels(['Item type', 'Status', 'Differences', 'Import'])
    self.table.verticalHeader().hide()
    self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.table.setWordWrap(True)
    self.comboBoxes:list[QComboBox] = []
    for row, entry in enumerate(comparison):
      self.table.setItem(row, 0, QTableWidgetItem(f"{entry['title']} ({entry['docType']})"))
      self.table.setItem(row, 1, QTableWidgetItem(STATUS[entry['status']]))
      differences = [f"{label}: {', '.join(entry[key])}" for key, label in
                     (('added','only in template'), ('removed','only here'), ('changed','changed')) if entry[key]]
      self.table.setItem(row, 2, QTableWidgetItem('\n'.join(differences)))
      self.comboBoxes.append(QComboBox())
      for action in entry['actions']:
        self.comboBoxes[-1].addItem(action.value, action)
      self.table.setCellWidget(row, 3, self.comboBoxes[-1])
    header = self.table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    self.table.resizeColumnsToContents()
    self.table.resizeRowsToContents()
    mainL.addWidget(self.table)
    footer = QHBoxLayout()
    footer.addStretch()
    Button('Cancel', self, Command.CANCEL, footer)
    Button('Import', self, Command.OK, footer, style=ButtonStyle.HIGHLIGHTED)
    mainL.addLayout(footer)


  def execute(self, command:'Command') -> None:
    """ Event if user clicks button

    Args:
      command (Command): command
    """
    if command is Command.CANCEL:
      self.reject()
    elif command is Command.OK:
      self.importActions = {entry['docType']:comboBox.currentData() for entry, comboBox in
                            zip(self.comparison, self.comboBoxes) if comboBox.currentData() is not ImportAction.SKIP}
      self.accept()


class Command(Enum):
  """ Commands used in this file """
  OK     = 1
  CANCEL = 2
