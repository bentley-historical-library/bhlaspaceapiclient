from datetime import datetime
import getpass
import requests
import json
from lxml import etree
import os
import re
import sys
import uuid

if sys.version_info[:2] <= (2, 7):
    # Python 2
    get_input = raw_input
    import ConfigParser as configparser
else:
    # Python 3
    get_input = input
    import configparser


class ArchivesSpaceError(Exception):
    pass


class ConnectionError(ArchivesSpaceError):
    pass


class AuthenticationError(ArchivesSpaceError):
    pass


class CommunicationError(ArchivesSpaceError):
    def __init__(self, status_code, response):
        message = "ArchivesSpace server responded {}".format(status_code)
        self.response = response
        super(CommunicationError, self).__init__(message)


class ASpaceClient(object):
    def __init__(self, instance_name=None, repository=2, expiring="true"):
        self.config_file = os.path.join(os.path.expanduser("~"), ".aspaceapi")
        configuration = self._load_config(instance_name)
        self.backend_url = configuration["backend_url"]
        self.frontend_url = configuration["frontend_url"]
        self.repository = "/repositories/{}".format(repository)
        self.username = configuration["username"]
        password = configuration.get("password")
        if not password:
            password = getpass.getpass("Enter password: ")
        self.expiring = expiring
        self._login(password)

    def _load_config(self, instance_name):
        config = configparser.RawConfigParser()
        config.read(self.config_file)
        instances = config.sections()
        if len(instances) == 0:
            print("No ArchivesSpace instances configured. Configure an instance? (y/n)")
            configure = get_input(": ")
            if configure.lower().strip() == "y" or configure.lower().strip() == "yes":
                configuration = self._add_instance(config)
                return configuration
            else:
                sys.exit()
        elif instance_name and instance_name in instances:
            configuration = {key: value for (
                key, value) in config.items(instance_name)}
            return configuration
        else:
            instance_mapping = {}
            instance_number = 0
            print("*** CONFIGURED INSTANCES ***")
            for instance in instances:
                instance_number += 1
                instance_mapping[str(instance_number)] = instance
                instance_url = config.get(instance, "backend_url")
                print("{} - {} [{}]".format(instance_number, instance, instance_url))
            print("A - Add Instance")
            option = get_input("Select an option: ")
            if option.strip() in instance_mapping.keys():
                instance = instance_mapping[option]
                configuration = {key: value for (
                    key, value) in config.items(instance)}
                return configuration
            elif option.lower().strip() == "a":
                configuration = self._add_instance(config)
                return configuration
            else:
                sys.exit()

    def _save_config(self, config):
        with open(self.config_file, "wb") as f:
            config.write(f)

    def _add_instance(self, config):
        instance_name = get_input("Instance name: ")
        backend_url = get_input("Backend URL: ")
        frontend_url = get_input("Frontend URL: ")
        username = get_input("Default username: ")
        store_password = get_input(
            "Store a password for this instance? (y/n) ")
        if store_password == "y":
            password = getpass.getpass("Enter password: ")
        else:
            password = False
        config.add_section(instance_name)
        config.set(instance_name, "backend_url", backend_url)
        config.set(instance_name, "frontend_url", frontend_url)
        config.set(instance_name, "username", username)
        if password:
            config.set(instance_name, "password", password)
        self._save_config(config)
        return {"backend_url": backend_url, "frontend_url": frontend_url, "username": username, "password": password}

    def _login(self, password):
        url = self.backend_url + "/users/" + self.username + "/login"
        params = {"password": password, "expiring": self.expiring}
        authenticate = requests.post(url, params=params).json()
        if authenticate.get("session", ""):
            self.session = requests.Session()
            token = authenticate["session"]
            self.session.headers.update({"X-ArchivesSpace-Session": token})
        else:
            print("Error logging in:")
            print(authenticate)
            sys.exit()

    def _request(self, method, url, params, expected_response, data=None):
        response = method(url, params=params, data=data)
        if response.status_code != expected_response:
            raise CommunicationError(response.status_code, response)

        try:
            response.json()
        except Exception:
            raise ArchivesSpaceError(
                "ArchivesSpace server responded with status {}, but returned a non-JSON document".format(response.status_code))

        return response

    def _get(self, url, params={}, expected_response=200):
        return self._request(self.session.get, url,
                             params=params,
                             expected_response=expected_response)

    def _put(self, url, params={}, data=None, expected_response=200):
        return self._request(self.session.put, url,
                             params=params, data=data,
                             expected_response=expected_response)

    def _post(self, url, params={}, data=None, expected_response=200):
        return self._request(self.session.post, url,
                             params=params, data=data,
                             expected_response=expected_response)

    def _delete(self, url, params={}, expected_response=200):
        return self._request(self.session.delete, url,
                             params=params,
                             expected_response=expected_response)

    def logout(self):
        url = self.backend_url + "/logout"
        self._post(url)

    def get_aspace_json(self, aspace_uri, params={}):
        url = "{}{}".format(self.backend_url, aspace_uri)
        return self._get(url, params=params).json()

    def post_aspace_json(self, aspace_uri, json=[], params={}):
        url = "{}{}".format(self.backend_url, aspace_uri)
        return self._post(url, params=params, json=json).json()

    def delete_aspace_object(self, aspace_uri, params={}):
        url = "{}{}".format(self.backend_url, aspace_uri)
        return self._delete(url, params=params).json()

    def update_aspace_object(self, aspace_uri, aspace_json, params={}):
        if aspace_uri == aspace_json["uri"]:
            return self.post_aspace_json(aspace_uri, json=aspace_json, params=params)
        else:
            raise ArchivesSpaceError("Unable to update object. Supplied URI {} does not match {}".format(
                aspace_uri, aspace_json["uri"]))

    def list_resources(self):
        uri = self.repository + "/resources"
        params = {"all_ids": True}
        return self.get_aspace_json(uri, params=params)

    def get_resource(self, resource_id):
        resource_uri = self.repository + "/resources/{}".format(resource_id)
        return self.get_aspace_json(resource_uri)

    def get_accession(self, accession_id):
        accession_uri = self.repository + "/accessions/{}".format(accession_id)
        return self.get_aspace_json(accession_uri)

    def get_subject(self, subject_id):
        subject_uri = "/subjects/{}".format(subject_id)
        return self.get_aspace_json(subject_uri)

    def get_agent(self, agent_uri):
        return self.get_aspace_json(agent_uri)

    def get_person(self, agent_person_id):
        agent_uri = "/agents/people/{}".format(agent_person_id)
        return self.get_agent(agent_uri)

    def get_corporate_entity(self, corporate_entity_id):
        agent_uri = "/agents/corporate_entities/{}".format(corporate_entity_id)
        return self.get_agent(agent_uri)

    def get_family(self, family_id):
        agent_uri = "/agents/families/{}".format(family_id)
        return self.get_agent(agent_uri)

    def get_digital_object(self, digital_object_id):
        digital_object_uri = self.repository + \
            "/digital_objects/{}".format(digital_object_id)
        return self.get_aspace_json(digital_object_uri)

    def get_archival_object(self, archival_object_id):
        archival_object_uri = self.repository + \
            "/archival_objects/{}".format(archival_object_id)
        return self.get_aspace_json(archival_object_uri)

    def get_archival_object_children(self, archival_object_id):
        uri = self.repository + \
            "/archival_objects/{}/children".format(archival_object_id)
        return self.get_aspace_json(uri)

    def post_archival_object_children(self, children, archival_object_id):
        uri = self.backend_url + self.repository + \
            "/archival_objects/{}/children".format(archival_object_id)
        archival_object_children = {
            "children": children, "jsonmodel_type": "archival_record_children"}
        response = self._post(uri, data=json.dumps(archival_object_children))
        return response.json()

    def get_bhl_classifications(self, aspace_json):
        classifications = []
        classification_fields = ["enum_1", "enum_2", "enum_3"]
        user_defined_fields = aspace_json["user_defined"]
        for classification_field in classification_fields:
            if user_defined_fields.get(classification_field):
                classifications.append(user_defined_fields[classification_field])
        return classifications

    def find_by_id(self, id_type, id_value):
        id_lookup_uri = self.repository + "/find_by_id/archival_objects"
        params = {"{}[]".format(id_type): id_value}
        id_lookup = self.get_aspace_json(id_lookup_uri, params=params)
        resolved_archival_objects = id_lookup["archival_objects"]
        if len(resolved_archival_objects) == 1:
            return {"success": resolved_archival_objects[0]["ref"]}
        else:
            return {"error": "Error resolving {} {}: {} archival objects returned".format(id_type, id_value, len(resolved_archival_objects))}

    def resolve_component_id(self, component_id):
        return self.find_by_id("component_id", component_id)

    def resolve_refid(self, ref_id):
        if ref_id.startswith("aspace_"):
            ref_id = ref_id.replace("aspace_", "")
        return self.find_by_id("ref_id", ref_id)

    def make_resource_link(self, resource_number):
        return "{}/resources/{}".format(self.frontend_url, resource_number)

    def transfer_archival_object(self, archival_object_uri, resource_uri):
        uri = "/repositories/2/component_transfers"
        params = {"target_resource": resource_uri,
                  "component": archival_object_uri}
        response = self.post_aspace_json(uri, params=params)
        event_to_delete = response["event"]
        self.delete_aspace_object(event_to_delete)
        return response

    def set_archival_object_parent(self, archival_object_id, parent_id, position=0):
        uri = "/repositories/2/archival_objects/{}/parent".format(
            archival_object_id)
        params = {"parent": int(parent_id), "position": position}
        response = self.post_aspace_json(uri, params=params)
        return response

    def make_archival_object_link_from_id(self, archival_object_id):
        archival_object = self.get_archival_object(archival_object_id)
        resource_ref = archival_object["resource"]["ref"]
        resource_number = resource_ref.split("/")[-1]
        return "{0}/resources/{1}#tree::archival_object_{2}".format(self.frontend_url, resource_number, archival_object_id)

    def make_archival_object_link_from_json(self, archival_object):
        resource_ref = archival_object["resource"]["ref"]
        resource_id = resource_ref.split("/")[-1]
        archival_object_uri = archival_object["uri"]
        return self.make_archival_object_link(resource_id, archival_object_uri)

    def make_archival_object_link(self, resource_number, aspace_uri):
        archival_object_number = aspace_uri.split("/")[-1]
        return "{0}/resources/{1}#tree::archival_object_{2}".format(self.frontend_url, resource_number, archival_object_number)

    def create_digital_object(self, title, link, identifier=False, publish=True, note_content="access item"):
        digital_object_json = {}
        digital_object_json["title"] = title
        if identifier:
            digital_object_json["digital_object_id"] = identifier
        else:
            digital_object_json["digital_object_id"] = str(uuid.uuid4())
        digital_object_json["publish"] = publish
        digital_object_json["notes"] = [{"type": "note", "content": [
            note_content], "publish": True, "jsonmodel_type":"note_digital_object"}]
        digital_object_json["file_versions"] = [
            {"file_uri": link, "xlink_show_attribute": "new", "xlink_actuate_attribute": "onRequest"}]
        return digital_object_json

    def post_digital_object(self, digital_object_json):
        uri = self.repository + "/digital_objects"
        return self.post_aspace_json(uri, json=digital_object_json)

    def make_digital_object_instance(self, digital_object_uri):
        return {'instance_type': 'digital_object', 'digital_object': {'ref': digital_object_uri}}

    def get_export_metadata(self, resource_number):
        uri = self.repository + \
            "/bhl_resource_descriptions/{}.xml/metadata".format(
                resource_number)
        return self.get_aspace_json(uri)

    def convert_ead_to_aspace_json(self, ead_filepath):
        self.session.headers.update(
            {"Content-type": "text/html; charset=utf-8"})
        uri = self.backend_url + "/plugins/jsonmodel_from_format/resource/ead"
        with open(ead_filepath, "rb") as f:
            response = self.session.post(uri, data=f).json()
        return response

    def export_ead(self, resource_number, include_unpublished=False, include_daos=True, numbered_cs=True, digitization_ead=False, default_ead=False):
        if digitization_ead:
            resource_description_uri = "/bhl_resource_descriptions_digitization/"
        elif default_ead:
            resource_description_uri = "/resource_descriptions/"
        else:
            resource_description_uri = "/bhl_resource_descriptions/"
        uri = self.backend_url + self.repository + \
            resource_description_uri + "{}.xml".format(resource_number)
        params = {
            "include_unpublished": include_unpublished,
            "include_daos": include_daos,
            "numbered_cs": numbered_cs
        }
        ead = self.session.get(uri, params=params)
        return ead

    def unpublish_aspace_object(self, uri):
        object_json = self.get_aspace_json(uri)
        if object_json["publish"]:
            object_json["publish"] = False
            resource_uri = self.backend_url + uri
            response = self.session.post(resource_uri, json=object_json).json()
        else:
            response = "{} already unpublished".format(uri)
        return response

    def unpublish_resource(self, resource_number):
        uri = self.repository + "/resources/{}".format(resource_number)
        response = self.unpublish_aspace_object(uri)
        return response

    def get_top_container_by_barcode(self, barcode):
        uri = self.repository + "/find_by_barcode/container"
        params = {"barcode": barcode}
        return self.get_aspace_json(uri, params=params)

    def get_top_container(self, container_id):
        uri = self.repository + "/top_containers/{}".format(container_id)
        return self.get_aspace_json(uri)

    def update_top_container(self, container_id, container_json):
        uri = self.repository + "/top_containers/{}".format(container_id)
        self.post_aspace_json(uri, json=container_json)

    def post_top_container(self, container_type, indicator, barcode=False):
        uri = self.backend_url + self.repository + "/top_containers"
        top_container = {"indicator": indicator,
                         "type": container_type, "jsonmodel_type": "top_container"}
        if barcode:
            top_container["barcode"] = barcode
        response = self._post(uri, data=json.dumps(top_container))
        return response.json()["uri"]

    def get_metadata_for_container(self, top_container_id):
        uri = self.repository + \
            "/metadata_for_container/{}".format(top_container_id)
        response = self.get_aspace_json(uri)
        return response

    def merge_top_containers(self, source_id, target_id):
        # replace all references to source with references to target and delete source
        archival_objects = self.get_metadata_for_container(source_id)[
            "archival_objects"]
        source_uri = self.repository + "/top_containers/{}".format(source_id)
        target_uri = self.repository + "/top_containers/{}".format(target_id)
        archival_object_uris = [archival_object["archival_object_uri"]
                                for archival_object in archival_objects]
        for archival_object_uri in archival_object_uris:
            archival_object = self.get_aspace_json(archival_object_uri)
            instances = archival_object["instances"]
            matching_instances = [
                instance for instance in instances if instance["sub_container"]["top_container"]["ref"] == source_uri]
            for matching_instance in matching_instances:
                matching_instance["sub_container"]["top_container"]["ref"] = target_uri
            self.update_aspace_object(archival_object_uri, archival_object)
        self.delete_aspace_object(source_uri)

    def get_resource_tree(self, resource_number):
        # /repositories/:repo_id/resources/:id/tree
        uri = self.backend_url + self.repository + \
            "/resources/{}/tree".format(resource_number)
        response = self._get(uri)
        return response.json()

    def get_enumeration(self, enumeration_id):
        uri = "/config/enumerations/{}".format(enumeration_id)
        enumeration = self.get_aspace_json(uri)
        return enumeration

    def update_enumeration(self, enumeration_id, enumeration):
        uri = "/config/enumerations/{}".format(enumeration_id)
        self.post_aspace_json(uri, json=enumeration)

    def add_enumeration_values(self, enumeration_id, new_enumeration_values):
        enumeration = self.get_enumeration(enumeration_id)
        values_to_add = [
            value for value in new_enumeration_values if value not in enumeration["values"]]
        if values_to_add:
            enumeration["values"].extend(values_to_add)
            self.update_enumeration(enumeration_id, enumeration)

    def remove_resource_associations(self, resource_number):
        resource_tree = self.get_resource_tree(resource_number)
        children_with_instances = find_children_with_instances(
            resource_tree["children"])
        instance_uris = []
        for child_uri in children_with_instances:
            instance_uris.extend(self.find_instance_uris(child_uri))
        for instance_uri in set(instance_uris):
            self.delete_single_resource_instances(instance_uri)

    def get_resource_children_with_instances(self, resource_number, instance_type=False):
        resource_tree = self.get_resource_tree(resource_number)
        children_with_instances = find_children_with_instances(
            resource_tree["children"], instance_type=instance_type)
        return children_with_instances

    def delete_single_resource_instances(self, instance_uri):
        if "digital_objects" in instance_uri:
            digital_object = self.get_aspace_json(instance_uri)
            if len(digital_object["linked_instances"]) == 1:
                self.delete_aspace_object(instance_uri)
        elif "top_containers" in instance_uri:
            top_container = self.get_aspace_json(instance_uri)
            if len(top_container["collection"]) == 1:
                self.delete_aspace_object(instance_uri)

    def find_instance_uris(self, aspace_uri, instance_type=False):
        instance_uris = []
        aspace_json = self.get_aspace_json(aspace_uri)
        instances = aspace_json["instances"]
        if instance_type:
            instances = [
                instance for instance in instances if instance["instance_type"] == instance_type]
        for instance in instances:
            if instance["instance_type"] == "digital_object":
                instance_uris.append(instance["digital_object"]["ref"])
            else:
                instance_uris.append(
                    instance["sub_container"]["top_container"]["ref"])
        return instance_uris

    def build_hierarchy(self, aspace_json, delimiter=">"):
        parent_titles = []
        while aspace_json.get("parent"):
            parent_ref = aspace_json["parent"]["ref"]
            parent_json = self.get_aspace_json(parent_ref)
            parent_title = self.make_display_string(parent_json)
            parent_titles.append(parent_title)
            aspace_json = parent_json
        parent_titles.reverse()
        if parent_titles:
            return " {} ".format(delimiter).join(parent_titles)
        else:
            return ""

    def make_display_string(self, aspace_json, add_parent_title=False):
        if aspace_json.get("title") and aspace_json.get("dates"):
            return self.sanitize_title(aspace_json["title"]) + ", " + self.format_dates(aspace_json)
        elif aspace_json.get("title") and not aspace_json.get("dates"):
            return self.sanitize_title(aspace_json["title"])
        elif aspace_json.get("dates") and not aspace_json.get("title"):
            if add_parent_title:
                parent_ref = aspace_json["parent"]["ref"]
                parent_json = self.get_aspace_json(parent_ref)
                parent_title = self.sanitize_title(
                    parent_json["display_string"])
                return parent_title + ", " + self.format_dates(aspace_json)
            else:
                return self.format_dates(aspace_json)

    def get_most_proximate_date(self, aspace_json):
        while not aspace_json.get("dates") and aspace_json.get("parent"):
            parent_ref = aspace_json["parent"]["ref"]
            aspace_json = self.get_aspace_json(parent_ref)

        return self.format_dates(aspace_json)

    def format_dates(self, aspace_json):
        if aspace_json.get("dates"):
            inclusive_dates = []
            bulk_dates = []
            for date in aspace_json["dates"]:
                expression = date.get("expression", "")
                if not expression:
                    begin = date.get("begin", "")
                    end = date.get("end", "")
                    if begin and end:
                        expression = "{}-{}".format(begin, end)
                    elif begin:
                        expression = begin
                if date["date_type"] == "inclusive":
                    inclusive_dates.append(expression.strip())
                if date["date_type"] == "bulk":
                    bulk_dates.append(expression.strip())
            dates = ", ".join(inclusive_dates)
            if bulk_dates:
                dates += " (bulk {})".format(bulk_dates[0])
            return dates
        else:
            return ""

    def sanitize_title(self, title):
        return re.sub(r"<.*?>", "", title).strip()

    def find_notes_by_type(self, aspace_json, note_type):
        matching_notes = [note for note in aspace_json["notes"]
                          if note.get("type") == note_type]
        if matching_notes:
            return matching_notes
        else:
            return ""

    def find_note_by_type(self, aspace_json, note_type):
        matching_notes = [note for note in aspace_json["notes"]
                          if note.get("type") == note_type]
        if matching_notes:
            return self.format_note(matching_notes[0])
        else:
            return ""

    def format_note(self, note):
        if note["jsonmodel_type"] == "note_singlepart":
            return note["content"][0]
        else:
            return note["subnotes"][0]["content"]

    def get_resource_archival_object_uris(self, resource_number):
        resource_tree = self.get_resource_tree(resource_number)
        archival_object_uris = extract_archival_object_uris_from_children(
            resource_tree["children"])
        return archival_object_uris

    def unpublish_expired_restrictions_for_resource(self, resource_number):
        today = datetime.today().strftime("%Y-%m-%d")
        archival_object_uris = self.get_resource_archival_object_uris(
            resource_number)
        unpublished_log = []
        for archival_object_uri in archival_object_uris:
            update_archival_object = False
            archival_object = self.get_aspace_json(archival_object_uri)
            for note in archival_object["notes"]:
                if note["type"] == "accessrestrict" and note["publish"]:
                    accessrestrict = self.format_note(note)
                    accessrestrict_xml = etree.fromstring(
                        "<accessrestrict>{}</accessrestrict>".format(accessrestrict))
                    accessrestrict_date = accessrestrict_xml.xpath("./date")
                    if accessrestrict_date and (accessrestrict_date[0].attrib["normal"] < today):
                        note["publish"] = False
                        update_archival_object = True
                        unpublished_log.append(
                            {"uri": archival_object_uri, "title": archival_object["display_string"], "restriction": accessrestrict})
            if update_archival_object:
                self.session.post(self.backend_url + archival_object_uri, json=archival_object).json()
        return unpublished_log

    def unpublish_restrictions_by_text(self, resource_number, restriction_text=False):
        if not restriction_text:
            return "No restriction text provided"
        archival_object_uris = self.get_resource_archival_object_uris(
            resource_number)
        unpublished_log = []
        for archival_object_uri in archival_object_uris:
            update_archival_object = False
            archival_object = self.get_aspace_json(archival_object_uri)
            for note in archival_object["notes"]:
                if note["type"] == "accessrestrict" and note["publish"]:
                    accessrestrict = self.format_note(note)
                    if accessrestrict == restriction_text:
                        note["publish"] = False
                        update_archival_object = True
                        unpublished_log.append(
                            {"uri": archival_object_uri, "title": archival_object["display_string"], "restriction": accessrestrict})
            if update_archival_object:
                self.session.post(self.backend_url + archival_object_uri, json=archival_object).json()
        return unpublished_log

    def parse_extents(self, aspace_json):
        parsed_extents = []
        if aspace_json.get("extents"):
            for extent in aspace_json["extents"]:
                parsed_extent = "{} {}".format(
                    extent["number"], extent["extent_type"])
                container_summary = extent.get("container_summary")
                physical_details = extent.get("physical_details")
                dimensions = extent.get("dimensions")
                parenthetical_parts = [attribute for attribute in [
                    container_summary, physical_details, dimensions] if attribute]
                if parenthetical_parts:
                    parenthetical = "; ".join(parenthetical_parts)
                    parsed_extent = "{} ({})".format(
                        parsed_extent, parenthetical)
                parsed_extents.append(parsed_extent)
        if parsed_extents:
            return "; ".join(parsed_extents)
        else:
            return ""
    
    def get_collection_id(self, resource_json):
        ead_id = resource_json.get("ead_id")
        identifier = resource_json["id_0"].strip()
        collection_id_regex = re.compile(r"^[\d\.]+")
        if ead_id:
            collection_id = "-".join(ead_id.split("-")[2:])
        elif collection_id_regex.match(identifier):
            collection_id = re.findall(r"^[\d\.]+", identifier)[0]
        else:
            collection_id = ""
        return collection_id

    def parse_link_from_digital_object(self, digital_object):
        if digital_object.get("file_versions"):
            return digital_object["file_versions"][0]["file_uri"]
        else:
            return digital_object["digital_object_id"]
    
    def get_digital_object_instance_links(self, aspace_json, match_pattern=False):
        links = []
        digital_object_instances = [instance for instance in aspace_json["instances"] if instance["instance_type"] == "digital_object"]
        for digital_object_instance in digital_object_instances:
            digital_object_uri = digital_object_instance["digital_object"]["ref"]
            digital_object = self.get_aspace_json(digital_object_uri)
            links.append(self.parse_link_from_digital_object(digital_object))
        if match_pattern:
            links = [link for link in links if match_pattern in link]
        return links

    def get_agents_by_role(self, aspace_json, role):
        agents = [agent["ref"] for agent in aspace_json["linked_agents"] if agent["role"] == role]
        return agents

    def get_first_agent_by_role(self, aspace_json, role):
        agents = self.get_agents_by_role(aspace_json, role)
        if agents:
            agent_uri = agents[0]
            agent_name = self.get_aspace_json(agent_uri)["title"]
            return self.verify_punctuation(agent_name)
        else:
            return ""

    def get_accession_source(self, accession_json):
        return self.get_first_agent_by_role(accession_json, "source")

    def get_resource_creator(self, resource_json):
        return self.get_first_agent_by_role(resource_json, "creator")

    def get_linked_agents(self, aspace_json):
        linked_agents = [agent for agent in aspace_json["linked_agents"]]
        return [self.construct_agent_name(linked_agent) for linked_agent in linked_agents]

    def construct_agent_name(self, linked_agent):
        agent_ref = linked_agent["ref"]
        agent_name = self.get_aspace_json(agent_ref)["title"]
        if linked_agent.get("terms"):
            if agent_name.endswith("."):
                agent_name = agent_name.rstrip(".")
            parts = [agent_name]
            parts.extend([term["term"] for term in linked_agent["terms"]])
            agent_name = " -- ".join(parts)
        return self.verify_punctuation(agent_name)

    def verify_punctuation(self, subject_or_agent):
        if not (subject_or_agent.endswith(".") or subject_or_agent.endswith(")") or subject_or_agent.endswith("-")):
            subject_or_agent += "."
        return subject_or_agent

    def get_linked_subjects(self, aspace_json, ignore_types=[]):
        subject_uris = [subject["ref"] for subject in aspace_json["subjects"]]
        subjects_json = [self.get_aspace_json(
            subject_uri) for subject_uri in subject_uris]
        return [self.verify_punctuation(subject["title"]) for subject in subjects_json if subject["terms"][0]["term_type"] not in ignore_types]


def extract_archival_object_uris_from_children(children, archival_object_uris=[]):
    for child in children:
        archival_object_uris.append(child["record_uri"])
        if child["has_children"]:
            extract_archival_object_uris_from_children(
                child["children"], archival_object_uris=archival_object_uris)
    return archival_object_uris


def find_children_with_instances(children, children_with_instances=[], instance_type=False):
    for child in children:
        if child["instance_types"]:
            if instance_type and instance_type in child["instance_types"]:
                children_with_instances.append(child["record_uri"])
            elif not instance_type:
                children_with_instances.append(child["record_uri"])
        if child["has_children"]:
            find_children_with_instances(
                child["children"], children_with_instances=children_with_instances, instance_type=instance_type)

    return children_with_instances
