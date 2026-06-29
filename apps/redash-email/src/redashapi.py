import time
from enum import Enum

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class APIError(Exception):
    pass


class JobStatus(Enum):
    PENDING = 1
    STARTED = 2
    SUCCESS = 3
    FAILURE = 4
    CANCELLED = 5


class Redash:
    def __init__(self, redash_url, redash_api_key):
        self.url = redash_url
        self.is_shared = {}
        csrf_token, cookies = self._obtain_csrf_token_and_cookies()
        self.headers = {
            "Authorization": f"Key {redash_api_key}",
            "Accept": "application/json",
            "X-CSRF-Token": csrf_token,
        }
        self._cookies = cookies

    def _obtain_csrf_token_and_cookies(self):
        redash_login_url = self.url.replace("api", "login")
        response = requests.head(redash_login_url, allow_redirects=True, verify=False)
        cookies = response.cookies
        if not cookies and response.history:
            cookies = response.history[0].cookies
        csrf_token = cookies.get("csrf_token")
        return csrf_token, cookies

    def get(self, endpoint, params=None):
        reply = requests.get(
            f"{self.url}/{endpoint}",
            params=params,
            headers=self.headers,
            cookies=self._cookies,
            verify=False,
        )
        reply.raise_for_status()
        return reply.json()

    def post(self, endpoint, data):
        reply = requests.post(
            f"{self.url}/{endpoint}",
            headers=self.headers,
            cookies=self._cookies,
            json=data,
            verify=False,
        )
        reply.raise_for_status()
        return reply.json()

    def delete(self, endpoint):
        reply = requests.delete(
            f"{self.url}/{endpoint}",
            headers=self.headers,
            cookies=self._cookies,
            verify=False,
        )
        reply.raise_for_status()
        return reply.json()

    def dashboard_id(self, name):
        reply = self.get("dashboards", {"page_size": 250})
        for dashboard in reply["results"]:
            if dashboard["name"] == name:
                return (dashboard["id"], dashboard["slug"])
        raise APIError(f"dashboard '{name}' not found")

    def dashboard_public_url(self, dashboard_id):
        reply = self.get(f"dashboards/{dashboard_id}")
        if "public_url" in reply:
            if dashboard_id not in self.is_shared:
                self.is_shared[dashboard_id] = True
            public_url = reply["public_url"]
        else:
            self.is_shared[dashboard_id] = False
            reply = self.post(f"dashboards/{dashboard_id}/share", {})
            public_url = reply["public_url"]
        return public_url

    def dashboard_reset(self, dashboard_id):
        if self.is_shared[dashboard_id] is False:
            self.delete(f"dashboards/{dashboard_id}/share")

    def dashboard_widget(self, dashboard_id, name):
        reply = self.get(f"dashboards/{dashboard_id}")
        for widget in reply["widgets"]:
            if "visualization" not in widget:
                continue
            query = widget["visualization"]["query"]
            if query["name"] == name and query["is_archived"] is False:
                parameters = query["options"]["parameters"]
                param_map = {}
                for param in parameters:
                    param_map[param["name"]] = param["value"]
                return (query["id"], param_map)
        raise APIError(f"query '{name}' not found for dashboard_id {dashboard_id}")

    def initiate_query(self, query_id, query_params):
        reply = self.post(f"queries/{query_id}/results", {"parameters": query_params})
        if "job" in reply:
            job_id = reply["job"]["id"]
            while reply["job"]["query_result_id"] is None:
                reply = self.get(f"jobs/{job_id}")
                status = reply["job"]["status"]
                if status == JobStatus.FAILURE:
                    raise APIError(f"job for query_id {query_id} failed")
                if status == JobStatus.CANCELLED:
                    raise APIError(f"job for query_id {query_id} canceled")
                time.sleep(2)
            return reply["job"]["query_result_id"]
        return reply["query_result"]["id"]
