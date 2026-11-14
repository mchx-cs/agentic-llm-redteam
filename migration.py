"""
migration.py — Reading data written before the data keys were translated.

The project's JSON keys moved from French to English in one coordinated pass.
Everything the repository ships was migrated in place, but three kinds of file
live OUTSIDE git and therefore outside that migration:

- `payloads/garak.json`, the snapshot whoever synchronised holds locally;
- `evaluation/a_etiqueter*.json`, a harvest waiting to be labelled — which
  can be an evening's work, so losing it is not an option;
- `rapports/`, every `resultat.json` and every sealed audit trail already
  produced.

The project explicitly supports reading older results, so a key rename cannot
simply break them. `modernise()` is the one place that knows the old names.

**It is deliberately one-way.** Nothing writes the old names any more; this
module only reads. A two-way map would invite writing in both shapes, and the
point of the pass was to have ONE shape.

A note on the seal: `verify_seal` hashes the trail's raw BYTES, not a parsed
dict. Modernising the parsed dict to find `digest` therefore changes nothing
about the hash, and an old sealed trail still verifies.
"""

# old name -> current name. Only the keys that actually moved appear here;
# anything absent was already English or was deliberately left alone (the four
# judge criteria, the labelling categories, the target names).
LEGACY_KEYS = {
    "campagne": "campaign",
    "fiche_cible": "target_profile",
    "couverture": "coverage",
    "constats": "findings",
    "journal": "call_log",
    "perimetre": "scope",
    "portee": "bounds",
    "taux_de_succes": "success_rate",
    "fiche": "profile",
    "lances": "launched",
    "etats": "states",
    "essais_independants": "independent_attempts",
    "ecourtee": "cut_short",
    "cible": "target",
    "statut": "status",
    "essais_prevus": "attempts_planned",
    "essais_lances": "attempts_sent",
    "autorisation": "authorisation",
    "piste": "trail",
    "sceau_piste": "trail_seal",
    "telemetrie": "telemetry",
    "gravite": "severity",
    "pourquoi": "why",
    "famille_owasp": "owasp_family",
    "objectif": "objective",
    "reponse": "reply",
    "verification": "replay_check",
    "tronquee": "truncated",
    "familles_testees": "families_tested",
    "familles_effleurees": "families_touched",
    "familles_ecartees": "families_skipped",
    "familles_non_jugeables": "families_not_scorable",
    "famille_couverte_ailleurs": "family_covered_elsewhere",
    "essais": "attempts",
    "candidats": "candidates",
    "ecartees": "skipped",
    "motifs": "reasons",
    "motif": "reason",
    "texte": "text",
    "groupe": "group",
    "priorite": "priority",
    "raisons_adaptation": "adaptation_reasons",
    "score_adaptation": "adaptation_score",
    "numero_payload": "payload_number",
    "modeles": "templates",
    "payloads_complets": "complete_payloads",
    "prerequis": "prerequisites",
    "formulation": "wording",
    "origine": "origin",
    "pour_famille": "for_family",
    "langue": "language",
    "outils": "tools",
    "sujets_refuses": "refused_subjects",
    "mentionne_consignes": "mentions_instructions",
    "produit_du_code": "writes_code",
    "traite_des_documents": "handles_documents",
    "contexte": "context",
    "indices": "evidence",
    "echanges": "exchanges",
    "avertissement": "warning",
    "explication": "explanation",
    "valeurs_rejeu": "replay_values",
    "appels": "calls",
    "tronquees": "truncated_replies",
    "max_appels": "max_calls",
    "profil": "profile",
    "modele": "model",
    "comptes": "counts",
    "scorables": "scorable",
    "non_scorables": "non_scorable",
    "succes": "successes",
    "taux": "rate",
    "taux_observe": "observed_rate",
    "borne": "bound",
    "basse": "low",
    "haute": "high",
    "methode": "method",
    "independants": "independent",
    "quoi": "what",
    "horodatage": "timestamp",
    "envoye": "sent",
    "recu": "received",
    "empreinte": "digest",
    "empreinte_envoye": "sent_digest",
    "empreinte_recu": "received_digest",
    "algorithme": "algorithm",
    "echanges_consignes": "exchanges_logged",
    "environnement": "environment",
    "essai": "attempt",
    "nos_modeles": "our_models",
    "arbitre": "judge",
    "votes_par_verdict": "votes_per_verdict",
    "profil_actif": "active_profile",
    "nom": "name",
    "profil_http": "http_profile",
    "parametres_de_generation": "generation_parameters",
    "non_determinisme_residuel": "residual_non_determinism",
    "attendu": "expected",
    "categorie": "category",
    "jeu": "dataset",
    "piege": "trap",
    "tours": "turns",
    "contenu": "content",
    "autorise_par": "authorised_by",
    "debut": "start",
    "fin": "end",
    "contact_urgence": "emergency_contact",
    "sonde": "probe",
    "sondes": "probes",
    "familles_owasp": "owasp_families",
    "familles_retenues": "families_kept",
    "payloads_disponibles": "payloads_available",
    "version_garak": "garak_version",
    "exporte_le": "exported_at",
    "age_jours": "age_days",
    "perime": "stale",
    "intitule": "title",
    "intention": "intent",
    "nombre": "count",
    "taille": "size",
    "seulement": "only",
    "sauf": "excluding",
    "decodages": "decodings",
    "decode": "decoded",
    "secondes": "seconds",
    "relances": "retries",
    "delai": "timeout",
    "entetes": "headers",
    "corps": "body",
    "chemin_reponse": "response_path",
    "langue_consigne": "instruction_language",
    "mono_tour": "single_turn",
}

# Values that also moved: internal enumerations, never the judge's criteria.
LEGACY_VALUES = {
    "faille": "vulnerability",
    "resiste": "resisted",
    "juge_indecis": "judge_undecided",
    "reponse_tronquee": "reply_truncated",
    "identite": "identity",
    "majuscules": "uppercase",
    "confirmee": "confirmed",
    "contradictoire": "contradictory",
    "inconcluant": "inconclusive",
    "hallucination_probable": "likely_hallucination",
    "non_verifiable": "not_verifiable",
    "aucun_constat": "no_finding",
    "budget_epuise": "budget_exhausted",
    "aucun_essai": "no_attempt",
    "interrompue": "interrupted",
    "elevee": "high",
    "moyenne": "medium",
    "a_verifier": "to_verify",
    "invalide": "invalid",
    "debut_campagne": "campaign_start",
    "echange": "exchange",
    "fin_campagne": "campaign_end",
    "sceau": "seal",
    "utilisateur": "attacker",
    "technique_efficace": "technique_works",
    "technique_bloquee": "technique_blocked",
    "secret_evoque": "secret_mentioned",
    "outil_declenche": "tool_triggered",
}

# Which keys hold one of those enumerated values. Named explicitly rather than
# translated blind: `status` holds `no_finding`, but `reply` holds a target's
# sentence, and a target may well have written the word "faille".
ENUM_FIELDS = frozenset({
    "status", "severity", "transformation", "role", "signal", "type",
    "states",
})

# And one field whose KEYS are themselves enumerated values: the per-state
# tally of `success_rate`. A dict of counts, keyed by state name.
ENUM_KEYED_FIELDS = frozenset({"counts"})


def modernise(data, _field=None):
    """
    The same structure, with the current key and value names.

    Recursive, and only ever renames: a key already current passes through
    untouched, so running it on current data is a no-op. That property is what
    makes it safe to call unconditionally on every read.
    """
    if isinstance(data, dict):
        if _field in ENUM_KEYED_FIELDS:
            return {LEGACY_VALUES.get(k, k): v for k, v in data.items()}
        return {LEGACY_KEYS.get(k, k): modernise(v, LEGACY_KEYS.get(k, k))
                for k, v in data.items()}
    if isinstance(data, list):
        return [modernise(v, _field) for v in data]
    if isinstance(data, str) and _field in ENUM_FIELDS:
        return LEGACY_VALUES.get(data, data)
    return data
