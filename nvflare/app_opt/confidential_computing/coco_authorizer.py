# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import requests
import time
import jwt
from jwt import PyJWKClient

from nvflare.app_opt.confidential_computing.cc_authorizer import CCAuthorizer

COCO_NAMESPACE = "x-ms"
maa_endpoint = 'sharedeus2.eus2.attest.azure.net'

class CoCoAuthorizer(CCAuthorizer):
    def generate(self):
        count = 0
        token = ""
        while True:
            count = count + 1
            try:
                r = requests.post('http://localhost:8284/attest/maa', data=json.dumps({"maa_endpoint": maa_endpoint, "runtime_data":  "ewp9"}), headers={"Content-Type" : "application/json"})
                if r.status_code == requests.codes.ok:
                    token = r.json().get("token")
                break
            except:
                if count > 5:
                    break
                time.sleep(2)
        return token
    
    def verify(self, token):
        try:
            header = jwt.get_unverified_header(token)
            # print(f"{header=}")
            alg = header.get('alg')
            jwks_client = PyJWKClient(f"https://{maa_endpoint}/certs")
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, signing_key.key, algorithms=[alg])
            if claims:
                # print(f"{claims=}")
                return True
        except:
            return False
        return False

    def can_generate(self) -> bool:
        return True

    def can_verify(self) -> bool:
        return True

    def get_namespace(self) -> str:
        return COCO_NAMESPACE

if __name__ == "__main__":
  m = CoCoAuthorizer()
  token = m.generate()
  print(type(token))
  v = m.verify(token)
  print(v)
