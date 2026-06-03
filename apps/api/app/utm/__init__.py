"""UTM attribution domain — source / medium / campaign dictionaries.

Turns the UTM params captured on form submissions into queryable dimensions
(Odoo `utm` module pattern): per-workspace dictionaries with find-or-create, so
analytics like "which channel brings deals" become a simple GROUP BY.
"""
