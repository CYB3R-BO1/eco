"""Parameterized Cypher templates.

Every query in this package is a module-level constant or a small builder
function. There is no string formatting on user-controlled input — only
on enum values (NodeType / RelationshipType). Parameters always pass via
``session.run(cypher, **params)`` so the driver handles binding.
"""
