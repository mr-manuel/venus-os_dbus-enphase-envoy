#!/usr/bin/env python

from time import time
from datetime import datetime
import json
# import requests
import os
import sys
import logging

from authentication import Authentication


class getToken:
    def __init__(self, user, password, serial, force=False):
        self.user = user
        self.password = password
        self.serial = serial
        self.force = force

    def refresh(self):
        token_file = "/data/etc/dbus-enphase-envoy/auth_token.json"
        # token_file = "./auth_token.json"

        if os.path.isfile(token_file):
            with open(token_file, "r") as file:
                file = open(token_file, "r")
                json_data = json.load(file)
        else:
            json_data = {"auth_token": "", "created": 0}

        # request a new token, if the old one is older than 12 hours
        if json_data["created"] + (60 * 60 * 12) - (60 * 5) < time():
            logging.warning(f"EnphaseToken: Token expired. Creation date: {datetime.fromtimestamp(json_data['created'])} UTC")

            try:
                token = Authentication()

                token.authenticate(self.user, self.password)

                response_data = token.get_token_for_commissioned_gateway(self.serial)

                json_data = {
                    "auth_token": response_data,
                    "created": int(time()),
                }

                with open(token_file, "w") as file:
                    file.write(json.dumps(json_data))

                logging.warning(f"EnphaseToken: Token successfully requested. New creation date: {datetime.fromtimestamp(json_data['created'])} UTC")

                return json_data

                """"
                data_login = {"user[email]": self.user, "user[password]": self.password}
                response_login = requests.post(
                    "https://enlighten.enphaseenergy.com/login/login.json",
                    data=data_login,
                )
                response_login_data = json.loads(response_login.text)

                if (
                    response_login_data["message"] == "success"
                    and "session_id" in response_login_data
                ):
                    logging.warning("EnphaseToken: Login success")

                    data = {
                        "session_id": response_login_data["session_id"],
                        "serial_num": self.serial,
                        "username": self.user,
                    }
                    response = requests.post(
                        "https://entrez.enphaseenergy.com/tokens", json=data
                    )
                    response_data = response.text

                    # check if response is a JSON, if yes a error occurred
                    try:
                        error = json.loads(response_data)
                        logging.error(
                            "EnphaseToken: Token request failed: " + error["message"]
                        )

                        return False

                    except ValueError:
                        json_data = {
                            "auth_token": response_data,
                            "created": int(time()),
                        }

                        with open(token_file, "w") as file:
                            file.write(json.dumps(json_data))

                        logging.warning("EnphaseToken: Token successfully requested")

                        return json_data

                else:
                    logging.error("EnphaseToken: " + response_data["message"])

                    return False
                """

            except Exception:
                exception_type, exception_object, exception_traceback = sys.exc_info()
                file = exception_traceback.tb_frame.f_code.co_filename
                line = exception_traceback.tb_lineno
                logging.error(
                    f"EnphaseToken: Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}"
                )

                return False

        else:
            logging.info(f"EnphaseToken: Token still valid. Creation date {datetime.fromtimestamp(json_data['created'])} UTC")
            return json_data


# code to test file directly
if __name__ == "__main__":
    print("Main run")
    token = getToken("user@domain.tld", "topsecret123", "123456789012")
    token.refresh()
