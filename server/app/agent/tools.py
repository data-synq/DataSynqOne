from simpleeval import simple_eval

from .. import db, vectorstore
from ..paperless_client import paperless_client
from .amount_extraction import extract_amounts_llm
from .query_expansion import expand_search_terms

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search Paperless documents by full-text query and optional correspondent id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Full-text search query"},
                    "correspondent_id": {"type": "integer", "description": "Filter by correspondent id"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document",
            "description": "Get full metadata and OCR text content of a single document by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                },
                "required": ["document_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_correspondents",
            "description": "List all correspondents known to Paperless.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_document_types",
            "description": "List all document types known to Paperless.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "Evaluate a safe arithmetic expression, e.g. for Nebenkostenabrechnungen, "
                "Prozentrechnung oder Summenbildung. Nutze dies statt selbst zu rechnen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "z. B. '1234.56 * 0.03' oder '(100 + 250) / 2'",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_amounts",
            "description": (
                "Extract all monetary amounts (with a short label each, e.g. 'Gesamtbetrag') "
                "from a single document's OCR text using an LLM."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                },
                "required": ["document_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents_by_amount",
            "description": (
                "Find documents whose extracted monetary amounts fall within a given range. "
                "Runs an LLM amount-extraction per candidate document, so set 'query' and/or "
                "'correspondent_id' to narrow down candidates first (max 'limit' documents checked)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "min_amount": {"type": "number"},
                    "max_amount": {"type": "number"},
                    "query": {"type": "string", "description": "Full-text search to narrow candidates"},
                    "correspondent_id": {"type": "integer"},
                    "limit": {"type": "integer", "description": "Max candidate documents to check (default 10)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_documents_by_tag",
            "description": "List documents that have a given tag (matched by name, case-insensitive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag_name": {"type": "string"},
                },
                "required": ["tag_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_documents_by_date_range",
            "description": "List documents created within a date range (YYYY-MM-DD), optionally combined with a search query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                    "query": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_documents",
            "description": "List the most recently added documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Default 10"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tags",
            "description": (
                "Listet alle in Paperless vorhandenen Tags auf. Status- und Kategorie-Tags folgen einer "
                "festen Taxonomie (siehe Systemanweisung) und existieren bereits. Nutze dieses Tool vor "
                "Klassifizierungs-/Organisationsaufgaben vor allem, um bereits vergebene, freie "
                "(nicht-taxonomische) Zusatz-Tags wiederzuverwenden statt neue, uneinheitliche zu erfinden."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_untagged_documents",
            "description": (
                "Liefert alle Dokumente, die aktuell KEINE Tags haben — zuverlaessig ueber die "
                "vollstaendige Dokumentliste ermittelt (kein serverseitiger Filter noetig). Nutze dies "
                "z. B. fuer 'tagge alle ungetaggten Dokumente'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max. Ergebnisse, Standard alle"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search_documents",
            "description": (
                "Semantische/inhaltliche Aehnlichkeitssuche ueber alle synchronisierten Paperless-"
                "Dokumente mittels Embeddings. Nutze dies fuer vage, thematische oder bedeutungsbasierte "
                "Anfragen, bei denen die exakte Keyword-Suche ('search_documents') relevante Dokumente "
                "verpassen koennte (z. B. 'Dokumente zu Wasserschaeden', 'irgendwas zur Heizungswartung')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "description": "Max. Ergebnisse, Standard 10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_tag",
            "description": "Erstellt einen neuen Tag (oder gibt den bestehenden zurueck, falls der Name schon existiert).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "color": {"type": "string", "description": "Optionale Hex-Farbe, z. B. '#a6cee3'"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_correspondent",
            "description": "Erstellt einen neuen Korrespondenten (oder gibt den bestehenden zurueck, falls der Name schon existiert).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_document_type",
            "description": "Erstellt einen neuen Dokumenttyp (oder gibt den bestehenden zurueck, falls der Name schon existiert).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assign_tags_to_document",
            "description": (
                "Weist einem Dokument einen oder mehrere Tags zu (additiv, bestehende Tags bleiben "
                "erhalten). Tags, die noch nicht existieren, werden automatisch angelegt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                    "tag_names": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["document_id", "tag_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_document_correspondent",
            "description": (
                "Setzt den Korrespondenten eines Dokuments. Der Korrespondent wird automatisch "
                "angelegt, falls er noch nicht existiert."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                    "correspondent_name": {"type": "string"},
                },
                "required": ["document_id", "correspondent_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_document_document_type",
            "description": (
                "Setzt den Dokumenttyp eines Dokuments. Der Dokumenttyp wird automatisch angelegt, "
                "falls er noch nicht existiert."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                    "document_type_name": {"type": "string"},
                },
                "required": ["document_id", "document_type_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_document",
            "description": "Aendert den Titel eines Dokuments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["document_id", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_tag",
            "description": "Loescht einen Tag unwiderruflich anhand seines Namens.",
            "parameters": {
                "type": "object",
                "properties": {"tag_name": {"type": "string"}},
                "required": ["tag_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_correspondent",
            "description": "Loescht einen Korrespondenten unwiderruflich anhand seines Namens.",
            "parameters": {
                "type": "object",
                "properties": {"correspondent_name": {"type": "string"}},
                "required": ["correspondent_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_document_type",
            "description": "Loescht einen Dokumenttyp unwiderruflich anhand seines Namens.",
            "parameters": {
                "type": "object",
                "properties": {"document_type_name": {"type": "string"}},
                "required": ["document_type_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bulk_update_documents",
            "description": (
                "Aendert Tags/Korrespondent/Dokumenttyp fuer viele Dokumente gleichzeitig in einem "
                "Rutsch. Ermittle die betroffenen Dokument-IDs vorher ueber ein Such-Tool "
                "(z. B. 'search_documents', 'filter_documents_by_tag') und uebergib sie hier gesammelt, "
                "statt die Einzel-Tools ('assign_tags_to_document' etc.) in einer Schleife pro Dokument "
                "aufzurufen. Namen, die noch nicht existieren, werden bei 'add_tag_names' automatisch "
                "angelegt (nicht bei 'remove_tag_names')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_ids": {"type": "array", "items": {"type": "integer"}},
                    "add_tag_names": {"type": "array", "items": {"type": "string"}},
                    "remove_tag_names": {"type": "array", "items": {"type": "string"}},
                    "correspondent_name": {"type": "string"},
                    "document_type_name": {"type": "string"},
                },
                "required": ["document_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_chart",
            "description": (
                "Render a chart (e.g. Kostenuebersicht, Verlauf ueber Zeit) for immediate display "
                "to the user. Gather/compute the numbers yourself first (search/amount/calculator "
                "tools), then call this with the final labels and datasets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie", "doughnut"]},
                    "title": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "datasets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "data": {"type": "array", "items": {"type": "number"}},
                            },
                            "required": ["label", "data"],
                        },
                    },
                    "x_label": {"type": "string"},
                    "y_label": {"type": "string"},
                },
                "required": ["chart_type", "title", "labels", "datasets"],
            },
        },
    },
]

RESPONSES_TOOL_DEFINITIONS = [{"type": "function", **t["function"]} for t in TOOL_DEFINITIONS]

_CHART_TYPES = {"bar", "line", "pie", "doughnut"}


def _create_chart(arguments: dict) -> dict:
    chart_type = arguments.get("chart_type")
    labels = arguments.get("labels") or []
    datasets = arguments.get("datasets") or []

    if chart_type not in _CHART_TYPES:
        return {"error": f"chart_type muss eines von {sorted(_CHART_TYPES)} sein"}
    if not labels:
        return {"error": "labels darf nicht leer sein"}
    if not datasets:
        return {"error": "datasets darf nicht leer sein"}
    for ds in datasets:
        if len(ds.get("data", [])) != len(labels):
            return {"error": f"dataset '{ds.get('label')}' hat nicht so viele Werte wie labels"}

    return {
        "chart_type": chart_type,
        "title": arguments.get("title", ""),
        "labels": labels,
        "datasets": datasets,
        "x_label": arguments.get("x_label"),
        "y_label": arguments.get("y_label"),
    }


async def _search_documents_by_amount(arguments: dict) -> dict:
    limit = arguments.get("limit") or 10
    candidates = await paperless_client.list_documents(
        query=arguments.get("query"),
        correspondent__id=arguments.get("correspondent_id"),
        page_size=limit,
    )
    min_amount = arguments.get("min_amount")
    max_amount = arguments.get("max_amount")

    matches = []
    for doc in candidates.get("results", []):
        amounts = await extract_amounts_llm(doc.get("content") or "")
        matched = [
            a
            for a in amounts
            if (min_amount is None or a["amount"] >= min_amount)
            and (max_amount is None or a["amount"] <= max_amount)
        ]
        if matched:
            matches.append({"id": doc["id"], "title": doc["title"], "amounts": matched})

    return {"checked": len(candidates.get("results", [])), "matches": matches}


async def _search_with_expansion(query: str | None, **filters) -> dict:
    result = await paperless_client.list_all_documents(query=query, **filters)

    if query and len(result.get("results", [])) < 3:
        variants = [v for v in await expand_search_terms(query) if v and v.lower() != query.lower()]
        if variants:
            seen_ids = {doc["id"] for doc in result["results"]}
            expanded_with = []
            for variant in variants:
                variant_result = await paperless_client.list_all_documents(query=variant, **filters)
                new_docs = [d for d in variant_result.get("results", []) if d["id"] not in seen_ids]
                if new_docs:
                    expanded_with.append(variant)
                    seen_ids.update(d["id"] for d in new_docs)
                    result["results"].extend(new_docs)
            if expanded_with:
                result["count"] = len(result["results"])
                result["expanded_with"] = expanded_with

    return result


async def _filter_documents_by_tag(tag_name: str) -> dict:
    tags = await paperless_client.list_tags()
    tag = next(
        (t for t in tags.get("results", []) if t["name"].lower() == tag_name.lower()),
        None,
    )
    if tag is None:
        return {"error": f"Tag '{tag_name}' nicht gefunden", "available_tags": [t["name"] for t in tags.get("results", [])]}
    return await paperless_client.list_all_documents(tags__id__in=str(tag["id"]))


async def _list_untagged_documents(limit: int | None) -> dict:
    all_docs = await paperless_client.list_all_documents(max_results=1000)
    untagged = [doc for doc in all_docs.get("results", []) if not doc.get("tags")]
    truncated = all_docs.get("truncated", False)
    if limit is not None and len(untagged) > limit:
        untagged = untagged[:limit]
        truncated = True
    return {"count": len(untagged), "results": untagged, "truncated": truncated}


async def _semantic_search_documents(arguments: dict) -> dict:
    query = arguments["query"]
    limit = arguments.get("limit") or 10
    embedding = await vectorstore.embed_query(query)
    results = await db.similarity_search(embedding, limit=limit)
    return {"results": results}


async def _get_or_create(list_fn, create_fn, name: str) -> dict:
    existing = await list_fn()
    match = next(
        (item for item in existing.get("results", []) if item["name"].lower() == name.lower()),
        None,
    )
    if match is not None:
        return match
    return await create_fn(name)


async def _find_by_name(list_fn, name: str) -> dict | None:
    existing = await list_fn()
    return next(
        (item for item in existing.get("results", []) if item["name"].lower() == name.lower()),
        None,
    )


async def _assign_tags_to_document(document_id: int, tag_names: list[str]) -> dict:
    doc = await paperless_client.get_document(document_id)
    tag_ids = set(doc.get("tags") or [])
    resolved = []
    for name in tag_names:
        tag = await _get_or_create(paperless_client.list_tags, paperless_client.create_tag, name)
        tag_ids.add(tag["id"])
        resolved.append(tag["name"])
    updated = await paperless_client.update_document(document_id, tags=list(tag_ids))
    return {"updated": True, "document_id": document_id, "tags_assigned": resolved}


async def _set_document_correspondent(document_id: int, correspondent_name: str) -> dict:
    correspondent = await _get_or_create(
        paperless_client.list_correspondents, paperless_client.create_correspondent, correspondent_name
    )
    await paperless_client.update_document(document_id, correspondent=correspondent["id"])
    return {"updated": True, "document_id": document_id, "correspondent": correspondent["name"]}


async def _set_document_document_type(document_id: int, document_type_name: str) -> dict:
    document_type = await _get_or_create(
        paperless_client.list_document_types, paperless_client.create_document_type, document_type_name
    )
    await paperless_client.update_document(document_id, document_type=document_type["id"])
    return {"updated": True, "document_id": document_id, "document_type": document_type["name"]}


async def _delete_tag(tag_name: str) -> dict:
    tag = await _find_by_name(paperless_client.list_tags, tag_name)
    if tag is None:
        return {"error": f"Tag '{tag_name}' nicht gefunden"}
    await paperless_client.delete_tag(tag["id"])
    return {"deleted": tag_name}


async def _delete_correspondent(correspondent_name: str) -> dict:
    correspondent = await _find_by_name(paperless_client.list_correspondents, correspondent_name)
    if correspondent is None:
        return {"error": f"Korrespondent '{correspondent_name}' nicht gefunden"}
    await paperless_client.delete_correspondent(correspondent["id"])
    return {"deleted": correspondent_name}


async def _delete_document_type(document_type_name: str) -> dict:
    document_type = await _find_by_name(paperless_client.list_document_types, document_type_name)
    if document_type is None:
        return {"error": f"Dokumenttyp '{document_type_name}' nicht gefunden"}
    await paperless_client.delete_document_type(document_type["id"])
    return {"deleted": document_type_name}


async def _bulk_update_documents(arguments: dict) -> dict:
    document_ids = arguments["document_ids"]
    applied = []
    errors = []

    for tag_name in arguments.get("add_tag_names") or []:
        tag = await _get_or_create(paperless_client.list_tags, paperless_client.create_tag, tag_name)
        await paperless_client.bulk_edit(document_ids, "add_tag", {"tag": tag["id"]})
        applied.append(f"add_tag: {tag['name']}")

    for tag_name in arguments.get("remove_tag_names") or []:
        tag = await _find_by_name(paperless_client.list_tags, tag_name)
        if tag is None:
            errors.append(f"Tag '{tag_name}' nicht gefunden, nicht entfernt")
            continue
        await paperless_client.bulk_edit(document_ids, "remove_tag", {"tag": tag["id"]})
        applied.append(f"remove_tag: {tag['name']}")

    correspondent_name = arguments.get("correspondent_name")
    if correspondent_name:
        correspondent = await _get_or_create(
            paperless_client.list_correspondents, paperless_client.create_correspondent, correspondent_name
        )
        await paperless_client.bulk_edit(document_ids, "set_correspondent", {"correspondent": correspondent["id"]})
        applied.append(f"set_correspondent: {correspondent['name']}")

    document_type_name = arguments.get("document_type_name")
    if document_type_name:
        document_type = await _get_or_create(
            paperless_client.list_document_types, paperless_client.create_document_type, document_type_name
        )
        await paperless_client.bulk_edit(document_ids, "set_document_type", {"document_type": document_type["id"]})
        applied.append(f"set_document_type: {document_type['name']}")

    return {"document_count": len(document_ids), "applied": applied, "errors": errors}


async def call_tool(name: str, arguments: dict) -> dict:
    if name == "search_documents":
        return await _search_with_expansion(
            arguments.get("query"),
            correspondent__id=arguments.get("correspondent_id"),
        )
    if name == "get_document":
        return await paperless_client.get_document(arguments["document_id"])
    if name == "list_correspondents":
        return await paperless_client.list_correspondents()
    if name == "list_document_types":
        return await paperless_client.list_document_types()
    if name == "calculator":
        try:
            return {"result": simple_eval(arguments["expression"])}
        except Exception as e:
            return {"error": str(e)}
    if name == "extract_amounts":
        doc = await paperless_client.get_document(arguments["document_id"])
        return {"amounts": await extract_amounts_llm(doc.get("content") or "")}
    if name == "search_documents_by_amount":
        return await _search_documents_by_amount(arguments)
    if name == "filter_documents_by_tag":
        return await _filter_documents_by_tag(arguments["tag_name"])
    if name == "filter_documents_by_date_range":
        return await _search_with_expansion(
            arguments.get("query"),
            created__date__gte=arguments.get("date_from"),
            created__date__lte=arguments.get("date_to"),
        )
    if name == "list_recent_documents":
        return await paperless_client.list_documents(
            ordering="-created",
            page_size=arguments.get("limit") or 10,
        )
    if name == "list_tags":
        return await paperless_client.list_tags()
    if name == "list_untagged_documents":
        return await _list_untagged_documents(arguments.get("limit"))
    if name == "semantic_search_documents":
        return await _semantic_search_documents(arguments)
    if name == "create_tag":
        return await _get_or_create(
            paperless_client.list_tags,
            lambda n: paperless_client.create_tag(n, color=arguments.get("color")),
            arguments["name"],
        )
    if name == "create_correspondent":
        return await _get_or_create(
            paperless_client.list_correspondents, paperless_client.create_correspondent, arguments["name"]
        )
    if name == "create_document_type":
        return await _get_or_create(
            paperless_client.list_document_types, paperless_client.create_document_type, arguments["name"]
        )
    if name == "assign_tags_to_document":
        return await _assign_tags_to_document(arguments["document_id"], arguments["tag_names"])
    if name == "set_document_correspondent":
        return await _set_document_correspondent(arguments["document_id"], arguments["correspondent_name"])
    if name == "set_document_document_type":
        return await _set_document_document_type(arguments["document_id"], arguments["document_type_name"])
    if name == "rename_document":
        return await paperless_client.update_document(arguments["document_id"], title=arguments["title"])
    if name == "delete_tag":
        return await _delete_tag(arguments["tag_name"])
    if name == "delete_correspondent":
        return await _delete_correspondent(arguments["correspondent_name"])
    if name == "delete_document_type":
        return await _delete_document_type(arguments["document_type_name"])
    if name == "bulk_update_documents":
        return await _bulk_update_documents(arguments)
    if name == "create_chart":
        return _create_chart(arguments)
    return {"error": f"unknown tool {name}"}
