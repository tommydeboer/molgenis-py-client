import json
import os

import requests

try:
    from urllib.parse import quote_plus
except ImportError:
    # Python 2
    from urllib import quote_plus


class Session:
    """Representation of a session with the MOLGENIS REST API.
sess
    Usage:
    >>> session = Session('http://localhost:8080/api/')
    >>> session.login('user', 'password')
    >>> session.get('Person')
    """

    def __init__(self, url="http://localhost:8080/api/"):
        """Constructs a new Session.
        Args:
        url -- URL of the REST API. Should be of form 'http[s]://<molgenis server>[:port]/api/'

        Examples:
        >>> session = Session('http://localhost:8080/api/')
        """
        self._url = url
        self._session = requests.Session()
        self._token = None

    def login(self, username, password):
        """Logs in a user and stores the acquired session token in this Session object.

        Args:
        username -- username for a registered molgenis user
        password -- password for the user
        """
        self._session.cookies.clear()
        response = self._session.post(self._url + "v1/login",
                                      data=json.dumps({"username": username, "password": password}),
                                      headers={"Content-Type": "application/json"})
        if response.status_code == 200:
            self._token = response.json()["token"]

        response.raise_for_status()
        return response

    def logout(self):
        """Logs out the current session token."""
        response = self._session.post(self._url + "v1/logout",
                                      headers=self._get_token_header())
        if response.status_code == 200:
            self._token = None
            self._session.cookies.clear()
        response.raise_for_status()
        return response

    def get_by_id(self, entity, id, attributes=None, expand=None):
        '''Retrieves a single entity row from an entity repository.

        Args:
        entity -- fully qualified name of the entity
        id -- the value for the idAttribute of the entity
        attributes -- The list of attributes to retrieve
        expand -- the attributes to expand

        Examples:
        session.get('Person', 'John')
        '''
        response = self._session.get(self._url + "v2/" + quote_plus(entity) + '/' + quote_plus(id),
                                     headers=self._get_token_header(),
                                     params={"attributes": attributes, "expand": expand})
        if response.status_code == 200:
            result = response.json()
            response.close()
            return result
        response.raise_for_status()
        return response

    def get(self, entity, q=None, attributes=None, num=100, start=0, sort_column=None, sort_order=None, raw=False,
            expand=None):
        """Retrieves entity rows from an entity repository.

        Args:
        entity -- fully qualified name of the entity
        q -- query in json form, see the MOLGENIS REST API v2 documentation for details
        attributes -- The list of attributes to retrieve
        expand -- the attributes to expand
        num -- the amount of entity rows to retrieve
        start -- the index of the first row to retrieve (zero indexed)
        sortColumn -- the attribute to sort on
        sortOrder -- the order to sort in
        raw -- when true, the complete REST response will be returned, rather than the data items

        Examples:
        session.get('Person')
        """
        possible_options = {'q':q,
                            'attrs':[attributes, expand],
                            'num':num,
                            'start':start,
                            'sort':[sort_column, sort_order]}


        url = self._build_api_url(self._url + "v2/" + entity, possible_options)
        response = self._session.get(url, headers=self._get_token_header())
        if response.status_code == 200:
            if not raw:
                return response.json()["items"]
            else:
                return response.json()
        response.raise_for_status()
        return response

    def add(self, entity, data=None, files=None, **kwargs):
        """Adds a single entity row to an entity repository.

        Args:
        entity -- fully qualified name of the entity
        files -- dictionary containing file attribute values for the entity row.
        The dictionary should for each file attribute map the attribute name to a tuple containing the file name and an
        input stream.
        data -- dictionary mapping attribute name to non-file attribute value for the entity row, gets merged with the
        kwargs argument
        **kwargs -- keyword arguments get merged with the data argument

        Examples:
        >>> session = Session('http://localhost:8080/api/')
        >>> session.add('Person', firstName='Jan', lastName='Klaassen')
        >>> session.add('Person', {'firstName': 'Jan', 'lastName':'Klaassen'})

        You can have multiple file type attributes.

        >>> session.add('Plot', files={'image': ('expression.jpg', open('~/first-plot.jpg','rb')),
        'image2': ('expression-large.jpg', open('/Users/me/second-plot.jpg', 'rb'))},
        data={'name':'IBD-plot'})
        """
        if not data:
            data = {}
        if not files:
            files = {}

        response = self._session.post(self._url + "v1/" + quote_plus(entity),
                                      headers=self._get_token_header(),
                                      data=self._merge_two_dicts(data, kwargs),
                                      files=files)
        if response.status_code == 201:
            return response.headers["Location"].split("/")[-1]
        response.raise_for_status()
        return response

    def add_all(self, entity, entities):
        """Adds multiple entity rows to an entity repository."""
        response = self._session.post(self._url + "v2/" + quote_plus(entity),
                                      headers=self._get_token_header_with_content_type(),
                                      data=json.dumps({"entities": entities}))
        if response.status_code == 201:
            return [resource["href"].split("/")[-1] for resource in response.json()["resources"]]
        else:
            errors = json.loads(response.content.decode("utf-8"))['errors'][0]['message']
            return errors

    def update_one(self, entity, id_, attr, value):
        """Updates one attribute of a given entity in a table with a given value"""
        response = self._session.put(self._url + "v1/" + quote_plus(entity) + "/" + id_ + "/" + attr,
                                     headers=self._get_token_header_with_content_type(),
                                     data=json.dumps(value))
        response.raise_for_status()
        return response

    def delete(self, entity, id_):
        """Deletes a single entity row from an entity repository."""
        response = self._session.delete(self._url + "v1/" + quote_plus(entity) + "/" + quote_plus(id_),
                                        headers=self._get_token_header())
        response.raise_for_status()
        return response

    def delete_list(self, entity, entities):
        """Deletes multiple entity rows to an entity repository, given a list of id's."""
        response = self._session.delete(self._url + "v2/" + quote_plus(entity),
                                        headers=self._get_token_header_with_content_type(),
                                        data=json.dumps({"entityIds": entities}))
        response.raise_for_status()
        return response

    def get_entity_meta_data(self, entity):
        """Retrieves the metadata for an entity repository."""
        response = self._session.get(self._url + "v1/" + quote_plus(entity) + "/meta?expand=attributes",
                                     headers=self._get_token_header())
        response.raise_for_status()
        return response.json()

    def get_attribute_meta_data(self, entity, attribute):
        """Retrieves the metadata for a single attribute of an entity repository."""
        response = self._session.get(self._url + "v1/" + quote_plus(entity) + "/meta/" + quote_plus(attribute),
                                     headers=self._get_token_header())
        response.raise_for_status()
        return response.json()

    def upload_zip(self, meta_data_zip):
        """Uploads a given zip with data and metadata"""
        header = self._get_token_header()
        files = {'file': open(os.path.abspath(meta_data_zip), 'rb')}
        url = self._url.strip('/api/') + '/plugin/importwizard/importFile'
        response = requests.post(url, headers=header, files=files)
        if response.status_code == 201:
            return response.content.decode("utf-8")
        response.raise_for_status()
        return response

    def _get_token_header(self):
        """Creates an 'x-molgenis-token' header for the current session."""
        try:
            return {"x-molgenis-token": self._token}
        except AttributeError:
            return {}

    def _get_token_header_with_content_type(self):
        """Creates an 'x-molgenis-token' header for the current session and a 'Content-Type: application/json' header"""
        headers = self._get_token_header()
        headers.update({"Content-Type": "application/json"})
        return headers

    def _build_api_url(self, base_url, possible_options):
        """This function builds the api url for the get request, converting the api v1 compliant operators to v2
        operators to enable backwards compatibility of the python api when switching to api v2"""
        operators = []
        for option in possible_options:
            option_value = possible_options[option]
            if option == 'q' and option_value:
                if type(option_value) == list:
                    raise TypeError('Your query should be specified in rsql format.')
                else:
                    operators.append('{}={}'.format(option, option_value))
            elif option == 'sort':
                if option_value[0]:
                    if option_value[1]:
                        operators.append('sort={}:{}'.format(option_value[0], option_value[1]))
                    else:
                        operators.append('sort='+option_value[0])
            elif option == 'attrs':
                attrs_operator = []
                if option_value[0]:
                    attrs_operator = option_value[0].split(',')
                    if option_value[1]:
                        expands = option_value[1].split(',')
                        attrs_operator = [operator+'(*)' if operator in expands else operator for operator in attrs_operator]
                    operators.append('attrs=' + ','.join(attrs_operator))
                elif option_value[1]:
                    expands = option_value[1].split(',')
                    attrs_operator = [attr+'(*)' for attr in expands]
                    attrs_operator.append('*')
                    operators.append('attrs='+','.join(attrs_operator))
            elif option_value and not (option == 'num' and option_value ==100):
                operators.append('{}={}'.format(option, option_value))

        url = '{}?{}'.format(base_url, '&'.join(operators))

        if url == base_url+'?':
            return base_url
        else:
            return url



    @staticmethod
    def _merge_two_dicts(x, y):
        """Given two dicts, merge them into a new dict as a shallow copy."""
        z = x.copy()
        z.update(y)
        return z
#json.loads(response.content.decode("utf-8"))['errors'][0]['message']
