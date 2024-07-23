import time

from django.shortcuts import render
from pymongo import MongoClient
import os
import sys
import ast
import dotenv
from pathlib import Path
from django.shortcuts import HttpResponse, redirect
from django.template import loader
from django.http import HttpResponseNotFound, JsonResponse
from django.utils.timesince import timesince
from django.utils import timezone
from nostr_sdk import Timestamp
from datetime import datetime
import json
import monitor.helpers as helpers
from bson import json_util
from django.utils.safestring import mark_safe
from .neo4j_service import neo4j_service
from general.dvm import EventKind


if os.getenv("USE_MONGITA", "False") != "False":  # use a local mongo db, like sqlite
    print("Using mongita")
    from mongita import MongitaClientDisk

    mongo_client = MongitaClientDisk()
    db = mongo_client.dvmdash
    print("Connected to local mongo db using MONGITA")
else:
    # connect to db
    mongo_client = MongoClient(os.getenv("MONGO_URI"))
    db = mongo_client["dvmdash"]

    try:
        result = db["events"].count_documents({})
        print(f"There are {result} documents in events collection")
    except Exception as e:
        print("Could not count documents in db")
        import traceback

        traceback.print_exc()

    print("Connected to cloud mongo db")


def metrics(request):
    # get the latest stats doc from the stats collection
    most_recent_stats = db.global_stats.find_one(sort=[("timestamp", -1)])

    template = loader.get_template("monitor/metrics.html")
    return HttpResponse(template.render(most_recent_stats, request))


def dvm(request, pub_key=""):
    print(f"Calling dvm with dvm_pub_key: {pub_key}")
    context = {}

    if pub_key == "":
        # get all dvm pub keys
        dvm_pub_keys = list(
            db.events.distinct(
                "pubkey",
                {
                    "kind": {
                        "$gte": 5000,
                        "$lte": 6999,
                        "$nin": EventKind.get_bad_dvm_kinds(),
                    }
                },
            )
        )

        # get all dvm pub key names from nip 89s
        dvm_nip89_profiles = {}

        for nip89_event in db.events.find({"kind": 31990}):
            if "pubkey" in nip89_event:
                try:
                    dvm_nip89_profiles[nip89_event["pubkey"]] = json.loads(
                        nip89_event["content"]
                    )
                    # print(
                    #     f"Successfully loaded json from nip89 event for pubkey {nip89_event['pubkey']}"
                    # )
                except Exception as e:
                    # print(f"Error loading json from {nip89_event['content']}")
                    # print(f"Content is: {nip89_event['content']}")
                    # print(e)
                    pass

        dvm_pub_keys_and_names = {}  # key is pub key or dvm name, value is pub key

        for pub_key in dvm_pub_keys:
            dvm_pub_keys_and_names[pub_key] = pub_key
            dvm_pub_keys_and_names[helpers.hex_to_npub(pub_key)] = pub_key
            if pub_key in dvm_nip89_profiles and "name" in dvm_nip89_profiles[pub_key]:
                dvm_pub_keys_and_names[dvm_nip89_profiles[pub_key]["name"]] = pub_key

        context["dvm_pub_keys_and_names"] = dvm_pub_keys_and_names

        template = loader.get_template("monitor/dvm.html")
        return HttpResponse(template.render(context, request))

    else:  # we have a specific dvm to return information for
        # get all events from this dvm_pub_key
        dvm_events = list(
            db.events.find({"pubkey": pub_key}).sort("created_at").limit(100)
        )

        # compute the number of results
        memory_usage = sys.getsizeof(dvm_events)
        print(f"Memory usage of dvm_events: {memory_usage}")

        context["dvm_pub_key"] = pub_key

        most_recent_stats = db.dvm_stats.find_one(
            {"metadata.dvm_npub_hex": pub_key}, sort=[("timestamp", -1)]
        )

        context.update(most_recent_stats)

        template = loader.get_template("monitor/dvm.html")
        return HttpResponse(template.render(context, request))


def kind(request, kind_num=""):
    print(f"Calling kind with kind_num: {kind_num}")
    context = {}

    if kind_num == "":
        # get all kinds
        kinds = list(db.events.distinct("kind"))

        context["kinds"] = kinds

        template = loader.get_template("monitor/kind.html")
        return HttpResponse(template.render(context, request))

    else:
        # load the data for this specific kind
        kind_num = int(kind_num)
        context["kind"] = kind_num

        most_recent_stats = db.kind_stats.find_one(
            {"metadata.kind_number": kind_num}, sort=[("timestamp", -1)]
        )

        context.update(most_recent_stats)

        # get most recent events
        recent_events = list(
            db.events.find({"kind": int(kind_num)}).sort("created_at").limit(100)
        )

        context["recent_events"] = recent_events

        template = loader.get_template("monitor/kind.html")
        return HttpResponse(template.render(context, request))


def see_event(request, event_id=""):
    print(f"Calling see_event with event_id: {event_id}")
    context = {}

    if event_id == "":
        # show a 404 page with a link back to the homepage
        template = loader.get_template("monitor/404.html")
        context[
            "message"
        ] = f"You have given a blank event ID. Please go back or go back to the homepage."
        return HttpResponseNotFound(template.render(context, request))

    # get the event with this id
    event = db.events.find_one({"id": event_id})

    if not event:
        # If no event is found, show a 404 page
        template = loader.get_template("monitor/404.html")
        context["message"] = f"Event with ID {event_id} was not found in our database."
        return HttpResponseNotFound(template.render(context, request))

    # Remove the '_id' field from the event dictionary
    event.pop("_id", None)

    # Convert the event to a JSON string using json_util to handle ObjectId
    # and process tags to convert 'p' tags to links
    event_str = json_util.dumps(event, indent=2)

    # Process the JSON string to convert 'p' tags to links
    event_data = json.loads(event_str)
    for tag in event_data.get("tags", []):
        if tag[0] == "e":
            tag[1] = f'<a href="/event/{tag[1]}/">{tag[1]}</a>'
        elif tag[0] == "p":
            tag[1] = f'<a href="/npub/{tag[1]}/">{tag[1]}</a>'
        elif tag[0] == "request":
            request_data = tag[1]
            print("Raw request data: ", request_data)
            request_as_json = json.loads(request_data)

            print(f"Request as json: {request_as_json}")

            if "kind" in request_as_json:
                request_as_json[
                    "kind"
                ] = f'<a href="/kind/{request_as_json["kind"]}/">{request_as_json["kind"]}</a>'

            if "id" in request_as_json:
                request_as_json[
                    "id"
                ] = f'<a href="/event/{request_as_json["id"]}/">{request_as_json["id"]}</a>'

            if "pubkey" in request_as_json:
                request_as_json[
                    "pubkey"
                ] = f'<a href="/npub/{request_as_json["pubkey"]}/">{request_as_json["pubkey"]}</a>'

            for sub_tag in request_as_json.get("tags", []):
                if sub_tag[0] == "e":
                    sub_tag[1] = f'<a href="/event/{sub_tag[1]}/">{sub_tag[1]}</a>'
                elif sub_tag[0] == "p":
                    sub_tag[1] = f'<a href="/npub/{sub_tag[1]}/">{sub_tag[1]}</a>'

            tag[1] = tag[1] = mark_safe(json.dumps(request_as_json, indent=8))

    if "pubkey" in event_data:
        event_data[
            "pubkey"
        ] = f'<a href="/npub/{event_data["pubkey"]}/">{event_data["pubkey"]}</a>'

        # event_data["request"] = request_as_json

    # Humanize the created_at timestamp
    created_at = datetime.fromtimestamp(event_data.get("created_at"))
    created_at_aware = timezone.make_aware(created_at, timezone.get_current_timezone())
    humanized_date = timesince(created_at_aware, timezone.now())

    # Add a description to the context
    context["event_description"] = (
        f"This is a KIND {event_data.get('kind')} event "
        f"created on {created_at_aware.strftime('%Y-%m-%d %H:%M:%S')} ({humanized_date} ago)."
    )

    # Convert the processed data back to a JSON string
    context["event"] = (
        json.dumps(event_data, indent=2).replace('\\"', '"').replace("\\n", "\n")
    )

    template = loader.get_template("monitor/event.html")
    return HttpResponse(template.render(context, request))


def see_npub(request, npub=""):
    print(f"Calling see_npub with npub: {npub}")
    context = {}

    if npub == "":
        # show a 404 page with a link back to the homepage and custom message
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render({"message": "Sorry, no npub was provided."}, request)
        )

    # see if we can get a nip-89 profile for this npub
    nip89_profile = db.events.find_one({"kind": 31990, "pubkey": npub})
    if nip89_profile:
        print("About to redirect with pub_key: ", npub)
        return redirect("dvm_with_pub_key", pub_key=npub)

    context["npub"] = npub

    # get the npub details (assuming `db.events` is your collection for npub data)
    npub_data_cursor = (
        db.events.find({"pubkey": npub}).sort("created_at", -1).limit(20)
    )  # -1 for descending order, limit to 20

    if not npub_data_cursor:
        # If no npub is found, show a 404 page with a custom message
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render(
                {"message": "Sorry, this npub isn't in our database."}, request
            )
        )

    npub_data = list(npub_data_cursor)  # Convert the cursor to a list

    # Process the event data to include human-readable timestamps
    for event in npub_data:
        if isinstance(event["created_at"], (int, float)):
            event["created_at"] = datetime.fromtimestamp(event["created_at"])

    context["npub_events"] = npub_data

    template = loader.get_template("monitor/npub.html")
    return HttpResponse(template.render(context, request))


def recent(request):
    num_events_to_lookback = 2000
    num_events_to_show_per_kind = 3
    context = {}
    recent_requests = list(
        db.events.find(
            {
                "kind": {
                    "$gte": 5000,
                    "$lte": 5999,
                    "$nin": EventKind.get_bad_dvm_kinds(),
                }
            }
        )
        .limit(num_events_to_lookback)
        .sort("created_at", -1)
    )

    print(f"Found {len(recent_requests)} recent requests")

    # recent requests per kind
    recent_requests_per_kind = {}
    recent_request_events = []
    kinds_already_filled = []  # make it faster
    for request_event in recent_requests:
        kind = request_event["kind"]
        if kind in kinds_already_filled:
            continue

        # make it readable on the frontend
        request_event["created_at"] = datetime.fromtimestamp(
            request_event["created_at"]
        )

        if kind in recent_requests_per_kind:
            if recent_requests_per_kind[kind] < num_events_to_show_per_kind:
                recent_requests_per_kind[kind] += 1
                recent_request_events.append(request_event)
            else:
                kinds_already_filled.append(kind)
        else:
            recent_requests_per_kind[kind] = 1
            recent_request_events.append(request_event)

    print(f"Found {len(recent_request_events)} recent requests (filtered)")

    # Convert the result to a list of dictionaries
    context["recent_dvm_events"] = recent_request_events

    print(f"context['recent_dvm_events'][0] = {context['recent_dvm_events'][0]}")

    template = loader.get_template("monitor/recent.html")
    return HttpResponse(template.render(context, request))


def debug(request, event_id=""):
    context = {}

    if event_id == "":
        # show a 404 page with a link back to the homepage and custom message
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render({"message": "Sorry, no event ID was provided."}, request)
        )

    # get the event with this id
    event = None
    events = list(db.events.find({"id": event_id}))
    print(f"events are {events}")
    if events:
        event = events[0]

    if not event:
        # show a 404 page with a link back to the homepage and custom message
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render(
                {"message": f"Event with ID {event_id} was not found in our database."},
                request,
            )
        )

    if "kind" in event and event["kind"] not in list(range(5000, 6000)):
        # show a 404 page with a link back to the homepage and custom message
        print(f"Event kind {event['kind']} is not supported for debugging")
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render(
                {
                    "message": "Sorry, only DVM requests in the range 5000-5999 are supported for now"
                },
                request,
            )
        )

    context["event_id"] = event["id"]

    template = loader.get_template("monitor/debug.html")
    return HttpResponse(template.render(context, request))


def about(request):
    context = {}
    template = loader.get_template("monitor/about.html")
    return HttpResponse(template.render(context, request))


def custom_404(
    request,
    exception=None,
    message="Sorry, the page you are looking for does not exist.",
):
    context = {"message": message}
    return render(request, "monitor/404.html", context, status=404)


def _get_row_data_from_event_dict(event_dict):
    """
    Helper function to parse results from neo4j

    Adds a 'quick_details' field to the event_dict if it doesn't already exist

    Returns the event id followed by the full event
    """

    if "id" not in event_dict:
        return None, event_dict

    already_processed_quick_details = False

    # if the kind is 7000, use the status field
    if (
        not already_processed_quick_details
        and "kind" in event_dict
        and event_dict["kind"] == 7000
    ):
        tags_str = event_dict["tags"]
        try:
            tags = ast.literal_eval(tags_str)
            for tag in tags:
                print(f"Looking at tag: {tag}")
                if isinstance(tag, list) and len(tag) >= 2 and tag[0] == "status":
                    event_dict["quick_details"] = "status: " + tag[-1]
                    already_processed_quick_details = True
                    break
        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {event_dict['id']}: {str(e)}")
            # Skip processing tags for this record and continue with the next one
            pass

    # use "content" field if it exists
    if not already_processed_quick_details:
        if "content" in event_dict and len(event_dict["content"]) > 0:
            event_dict["quick_details"] = event_dict["content"]
            already_processed_quick_details = True

    # as a last resort, try the 'i' tag
    if not already_processed_quick_details and "tags" in event_dict:
        tags_str = event_dict["tags"]
        try:
            tags = ast.literal_eval(tags_str)
            for tag in tags:
                print(f"Looking at tag: {tag}")
                if isinstance(tag, list) and len(tag) >= 2 and tag[0] == "i":
                    event_dict["quick_details"] = tag[1]
                    already_processed_quick_details = True
                    break
        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {event_dict['id']}: {str(e)}")
            # Skip processing tags for this record and continue with the next one
            pass

    # for invoices, use a message with the amount and a clickable lighting invoice for quick details
    if (
        not already_processed_quick_details
        and "amount" in event_dict
        and "invoice" in event_dict
        and "creator_pubkey" in event_dict
    ):
        amount_millisats = int(event_dict["amount"])
        invoice_str = event_dict["invoice"]
        creator_pubkey_str = event_dict["creator_pubkey"]
        event_dict["pubkey"] = creator_pubkey_str

        event_dict[
            "quick_details"
        ] = f'Invoice for {amount_millisats / 1000 :.2f} sats (<a href="lightning:${invoice_str}">Click to Pay</a>)'
        already_processed_quick_details = True

    if already_processed_quick_details:
        # check to see if the value is a link and if so, make a url
        if event_dict["quick_details"].startswith("http"):
            event_dict[
                "quick_details"
            ] = f'<a href="{event_dict["quick_details"]}">Link</a>'

    return event_dict["id"], event_dict


def get_graph_data(request, request_event_id=""):
    """
    Note this is for the api endpoint /graph/ for neoviz.js, not to render a django template
    """

    # now call neo 4j to get the graph data
    query = (
        """
        MATCH (req:Event {id: '"""
        + request_event_id
        + """'})
        OPTIONAL MATCH (n)-[r*]->(req)
        RETURN n, r, req
        """
    )

    print("Querying neo4j with query: ", query)

    data = neo4j_service.run_query(query)

    # process the data so it's in an easy format for forming into a graph
    # these will all be triples
    node_relations = []

    # print("Got data from neo4j:")
    # print(json.dumps(data, indent=2, sort_keys=True))

    event_nodes = {}  # key is the event id, value is the event node
    for record in data:
        if "n" not in record:
            print("WARNING!!!! 'n' is not in record:")
            record_str = json.dumps(record, indent=2, sort_keys=True)
            print(f"Record: {record_str}")
            continue

        if "req" not in record:
            print("WARNING!!!! 'req' is not in record:")
            record_str = json.dumps(record, indent=2, sort_keys=True)
            print(f"Record: {record_str}")
            continue

        n_event_id, n_event_data = _get_row_data_from_event_dict(record["n"])
        if n_event_id and n_event_id not in event_nodes.keys():
            event_nodes[n_event_id] = n_event_data
        if "n_type" in record and "neo4j_node_type" not in n_event_data:
            n_event_data["neo4j_node_type"] = record["n_type"]

        req_event_id, req_event_data = _get_row_data_from_event_dict(record["req"])
        if req_event_id and req_event_id not in event_nodes.keys():
            event_nodes[req_event_id] = req_event_data
        if "req_type" in record and "neo4j_node_type" not in req_event_data:
            req_event_data["neo4j_node_type"] = record["req_type"]

        for relation in record["r"]:
            lhs = relation[0]
            relation_name = relation[1]
            rhs = relation[2]

            # if the relation is between two events, add it to the list
            node_relations.append(
                {
                    "source_node": lhs,
                    "target_node": rhs,
                    "relation": relation_name,
                }
            )

    response_data = {
        "data": data,
        "event_nodes": list(event_nodes.values()),
        "node_relations": node_relations,
    }

    return JsonResponse(response_data, safe=False)


def playground(request):
    context = {}
    template = loader.get_template("monitor/playground.html")
    return HttpResponse(template.render(context, request))
