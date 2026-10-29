"""Le pilotage n'a pas de table : il lit celles des autres applications.

Ce module existe pour que Django envoie à ``reporting`` les signaux
``pre_migrate`` et ``post_migrate`` — il ne les envoie qu'aux applications
qui ont des modèles —, par lesquels se reposent les vues du schéma ``bi``
(``reporting.bi``, décision 122).
"""
