.. _definitions:

Definitions and Data Hierarchy
==============================

.. raw:: html

   <div class="three-columns">
      <a href="index.html" class="back-button" style="flex: 1; height: 25px;"><b>&larr; Back</b></a>
      <div style="flex: 12;">
         <h2>Define Data Schema and Definitions</h2>
      </div>
   </div>

**Overview**: Define metadata structures and data types (data schema) for projects via a :ref:`Editors <dataSchemeEditor>`. Specify terms and URLs to relate to ontologies in a separate :ref:`GUI <definitionGUI>`.

.. _dataSchemeEditor:

Data Schema Editor
------------------

Located under "Project Group," the editor allows users to:

1. Select, edit, or create data types.
2. Specify metadata in a table, including:
   - **Description**
   - **Unit**
   - **Mandatory status**
   - **List**: Link metadata to fixed lists (e.g., devices: "Oven," "Fume hood") or other data types (e.g., procedures).

**Note**: Metadata must be unique and include a name, tags, and comments in the general tab.

.. _itemTemplates:

Templates
---------

Templates are JSON files that share item types and items between project groups and with other people.

* **Export item types**: In the item type editor, select **Export…** and select the item types. The template contains
  their fields, units, lists, and descriptions.
* **Import item types**: In the item type editor, select **Import…** and select a template. A preview compares each
  item type with the project group and offers the actions **Add** (new item types), **Add missing fields** (existing
  fields stay unchanged), **Replace** (also removes fields that are not in the template), and **Skip**. Nothing is
  changed before **Import** is selected.
* **Export an item**: In the Details pane, select **Export as template…**. The template contains the item type and the
  item's keys and units, and optionally its values, comment, and tags. Links to other items and vendor/user metadata
  are left out.
* **New item from a template**: Above a list, select **More > New item from template…**. The form opens with the keys
  and values of the template. If the item type is missing, import it first.

.. _definitionGUI:

Definition Overview
-------------------

Scientific properties require detailed definitions. For example:

.. code-block::

    temperature_A : 97

Here, **temperature_A** is the **key**, and 97 is the **value**. However, additional details like:

- **Scientific unit**
- **Description**
- **PURL/IRI**

are essential. A complete representation:

.. code-block::

    temperature_A : {
        'value': 97,
        'unit': 'C',
        'description': 'Temperature inside the instrument’s right side',
        'PURL': 'https://www.wikidata.org/wiki/Q11466'}

Additional metadata can include:

- **Uncertainty**: Margin of error.
- **Data type**: Integer, text, date, etc.
- **Allowable values**: E.g., temperatures cannot be below 0 K.

PASTA-ELN balances usability and flexibility, allowing most metadata in the **value** or **description** fields.

Handling Multiple Datasets and Data Types
-----------------------------------------

To avoid duplication, PASTA-ELN stores **description** and **PURL** for each **key** in a centralized table (*definitions*). The **value** and **unit** can be stored independently or inherit from the master definition. If both individual and master definitions specify a unit, the individual value's unit takes precedence.

This ensures each **key** is unique. For example:

- "Height" defined for instruments applies to samples, sharing the same **description** and **PURL** but potentially differing in units.
- Unique **keys** are required for distinct descriptions.

.. raw:: html

   <a href="index.html" class="back-button" style="flex: 1; height: 25px;"><b>&larr; Back</b></a>
   <span style="float: right"><img src="_static/pasta_logo.svg" alt="logo" style="width: 60px;"/></span>
