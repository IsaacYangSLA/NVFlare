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


from nvflare.app_opt.confidential_computing.cc_authorizer import CCAuthorizer
import json
import jwt

from nv_attestation_sdk import attestation
import os 

GPU_NAMESPACE = "x-nv-gpu-"

class GPUAuthorizer(CCAuthorizer):
    def __init__(self, verifier_url="https://nras.attestation.nvidia.com/v1/attest/gpu"):
        self.can_generate = True
        self.client = attestation.Attestation()
        self.client.set_name("thisNode1")
        self.client.set_nonce("931d8dd0add203ac3d8b4fbde75e115278eefcdceac5b87671a748f32364dfcb")
        self.client.add_verifier(attestation.Devices.GPU, attestation.Environment.REMOTE, verifier_url, "")
        file = "NVGPURemotePolicyExample.json"
        with open(os.path.join(os.path.dirname(__file__), file)) as json_file:
            json_data = json.load(json_file)
            self.remote_att_result_policy = json.dumps(json_data)

    def generate(self):
        try:
            self.client.attest()
            token = self.client.get_token()
        except BaseException:
            self.can_generate = False
            token = "[[],{}]"
        return token
    
    def verify(self, eat_token):
        try:
            # header = jwt.get_unverified_header(jwt_token[1])
            # # url = header.get("jku")
            # alg = header.get('alg')
            # jwks_client = PyJWKClient(self.verifier_url)
            # signing_key = jwks_client.get_signing_key_from_jwt(jwt_token)
            jwt_token = json.loads(eat_token)[1]
            # pprint.pprint(f"{jwt_token=}")
            claims = jwt.decode(jwt_token.get("REMOTE_GPU_CLAIMS"), options={"verify_signature": False})
            # pprint.pprint(f"{claims=}")
            nonce = claims.get('eat_nonce')
            self.client.set_name("nvflare_node1")
            # self.client.set_nonce("931d8dd0add203ac3d8b4fbde75e115278eefcdceac5b87671a748f32364dfcb")
            self.client.set_nonce(nonce)
            self.client.set_token(name='nvflare_node1', eat_token=eat_token)
            result = self.client.validate_token(self.remote_att_result_policy)
        except BaseException:
            result = False
        return result

    def can_generate(self) -> bool:
        return self.can_generate

    def can_verify(self) -> bool:
        return True

    def get_namespace(self) -> str:
        return GPU_NAMESPACE
