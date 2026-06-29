"""Custom NER extraction of booking details from cleaned email text.

A spaCy NER model (trained separately, see `NER model creation.ipynb`) tags the
email body with custom entities (ORDER, DATE, TIME, FROM, TO, PAX, etc.). This
module turns those entities into a structured dict, and detects whether the
enquiry is a one-way trip (one of each field) or a return (two of each).
"""

import spacy

from logging_config import logger

ENTITY_KEYS = [
    "Order", "Name", "Date", "Time", "From", "To", "Extras",
    "Total", "Deposit", "Pax", "Phone", "Details", "Address",
]
ENTITY_LABELS = [
    "ORDER", "PERSON", "DATE", "TIME", "FROM", "TO", "EXTRAS",
    "TOTAL", "DEPOSIT", "PAX", "PHONE", "DETAILS", "ADDRESS",
]


def _resolve_deposit(values):
    """Deposit may be absent, explicitly stated, or need a manual query."""
    if len(values) == 0:
        return " "
    if any("deposit" in v for v in values):
        return [s for s in values if "deposit" in s][0]
    return "query"


def ner(email):
    """Run the NER model over the email and return structured booking fields.

    Returns a single dict for a one-way trip, a (dict, dict) tuple for a return
    booking, or None if the extracted entities are inconsistent.
    """
    nlp = spacy.load("model-best-gpu")
    doc = nlp(email)

    collected = {label: [] for label in ENTITY_LABELS}
    for ent in doc.ents:
        if ent.label_ in collected:
            collected[ent.label_].append(ent.text)

    values = [collected[label] for label in ENTITY_LABELS]
    date, time, frm, to = collected["DATE"], collected["TIME"], collected["FROM"], collected["TO"]
    legs = (date, time, frm, to)

    if all(len(lst) == 1 for lst in legs):
        # One-way booking: collapse each field to a single value
        variables = dict(zip(ENTITY_KEYS, values))
        for key in variables:
            if key == "Deposit":
                variables[key] = _resolve_deposit(variables[key])
            elif len(variables[key]) == 0:
                variables[key] = " "
            else:
                variables[key] = variables[key][0]
        return variables

    if all(len(lst) == 2 for lst in legs):
        # Return booking: split into outbound (A) and inbound (B) legs
        variables_a = dict(zip(ENTITY_KEYS, [list(v) for v in values]))
        variables_b = dict(zip(ENTITY_KEYS, [list(v) for v in values]))
        for key in variables_a:
            if key == "Deposit":
                variables_a[key] = _resolve_deposit(variables_a[key])
            elif len(variables_a[key]) == 0:
                variables_a[key] = " "
            else:
                variables_a[key] = variables_a[key][0]
        for key in variables_b:
            if key == "Deposit":
                variables_b[key] = _resolve_deposit(variables_b[key])
                continue
            if len(variables_b[key]) == 0:
                variables_b[key] = " "
            elif len(variables_b[key]) >= 2:
                variables_b[key] = variables_b[key][1]
            else:
                variables_b[key] = variables_b[key][0]
        return variables_a, variables_b

    logger.error("Data load fail details: %s", legs)
    return None
