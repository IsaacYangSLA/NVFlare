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

test_token = '[["JWT", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJOVi1BdHRlc3RhdGlvbi1TREsiLCJpYXQiOjE3MDg0NTc2NDgsImV4cCI6bnVsbH0.zQ3Z4IEdudYoeMXBFz_Uub2WHaQBd6cPCCc6javkOzs"], {"REMOTE_GPU_CLAIMS": "eyJraWQiOiJudi1hdHRlc3RhdGlvbi1zaWduLWtpZC1wcm9kLTIwMjQwMjIwMTEzODI4IiwiYWxnIjoiRVMzODQifQ.eyJzdWIiOiJOVklESUEtR1BVLUFUVEVTVEFUSU9OIiwic2VjYm9vdCI6dHJ1ZSwieC1udmlkaWEtZ3B1LW1hbnVmYWN0dXJlciI6Ik5WSURJQSBDb3Jwb3JhdGlvbiIsIngtbnZpZGlhLWF0dGVzdGF0aW9uLXR5cGUiOiJHUFUiLCJpc3MiOiJodHRwczpcL1wvbnJhcy5hdHRlc3RhdGlvbi5udmlkaWEuY29tIiwiZWF0X25vbmNlIjoiMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMSIsIngtbnZpZGlhLWF0dGVzdGF0aW9uLWRldGFpbGVkLXJlc3VsdCI6eyJ4LW52aWRpYS1ncHUtZHJpdmVyLXJpbS1zY2hlbWEtdmFsaWRhdGVkIjp0cnVlLCJ4LW52aWRpYS1ncHUtdmJpb3MtcmltLWNlcnQtdmFsaWRhdGVkIjp0cnVlLCJ4LW52aWRpYS1ncHUtYXR0ZXN0YXRpb24tcmVwb3J0LWNlcnQtY2hhaW4tdmFsaWRhdGVkIjp0cnVlLCJ4LW52aWRpYS1ncHUtZHJpdmVyLXJpbS1zY2hlbWEtZmV0Y2hlZCI6dHJ1ZSwieC1udmlkaWEtZ3B1LWF0dGVzdGF0aW9uLXJlcG9ydC1wYXJzZWQiOnRydWUsIngtbnZpZGlhLWdwdS1ub25jZS1tYXRjaCI6dHJ1ZSwieC1udmlkaWEtZ3B1LXZiaW9zLXJpbS1zaWduYXR1cmUtdmVyaWZpZWQiOnRydWUsIngtbnZpZGlhLWdwdS1kcml2ZXItcmltLXNpZ25hdHVyZS12ZXJpZmllZCI6dHJ1ZSwieC1udmlkaWEtZ3B1LWFyY2gtY2hlY2siOnRydWUsIngtbnZpZGlhLWF0dGVzdGF0aW9uLXdhcm5pbmciOm51bGwsIngtbnZpZGlhLWdwdS1tZWFzdXJlbWVudHMtbWF0Y2giOnRydWUsIngtbnZpZGlhLWdwdS1hdHRlc3RhdGlvbi1yZXBvcnQtc2lnbmF0dXJlLXZlcmlmaWVkIjp0cnVlLCJ4LW52aWRpYS1ncHUtdmJpb3MtcmltLXNjaGVtYS12YWxpZGF0ZWQiOnRydWUsIngtbnZpZGlhLWdwdS1kcml2ZXItcmltLWNlcnQtdmFsaWRhdGVkIjp0cnVlLCJ4LW52aWRpYS1ncHUtdmJpb3MtcmltLXNjaGVtYS1mZXRjaGVkIjp0cnVlLCJ4LW52aWRpYS1ncHUtdmJpb3MtcmltLW1lYXN1cmVtZW50cy1hdmFpbGFibGUiOnRydWUsIngtbnZpZGlhLWdwdS1kcml2ZXItcmltLWRyaXZlci1tZWFzdXJlbWVudHMtYXZhaWxhYmxlIjp0cnVlfSwieC1udmlkaWEtdmVyIjoiMS4wIiwibmJmIjoxNzA4NDU3NjYwLCJ4LW52aWRpYS1ncHUtZHJpdmVyLXZlcnNpb24iOiI1MzUuMTI5LjAzIiwiZGJnc3RhdCI6ImRpc2FibGVkIiwiaHdtb2RlbCI6IkdIMTAwIEEwMSBHU1AgQlJPTSIsIm9lbWlkIjoiNTcwMyIsIm1lYXNyZXMiOiJjb21wYXJpc29uLXN1Y2Nlc3NmdWwiLCJleHAiOjE3MDg0NjEyNjAsImlhdCI6MTcwODQ1NzY2MCwieC1udmlkaWEtZWF0LXZlciI6IkVBVC0yMSIsInVlaWQiOiI0NTk0NzY0OTYzNDkzMTY2MDEyOTUyNDk1Njc0MzMwMjk1MDIxOTIyNTkwNTA3ODgiLCJ4LW52aWRpYS1ncHUtdmJpb3MtdmVyc2lvbiI6Ijk2LjAwLjc0LjAwLjExIiwianRpIjoiMWMzM2FmMGEtYTFkOS00NzlhLWIyYmItNjNlNjRkNWRlYjAyIn0.xPfLlzfVS3_R4KF14QQjAEzqW4b7BrSzQBfiFZebhS_lrQbcbchcq3G3ZnyC97bvVW2G5tWOzKswYGoqxuzz7851b65yxVuVzlAo3dY2rao9k6-1a_t9Q3IaPCPyDnYL"}]'

GPU_NAMESPACE = "x-nv-gpu-"
policy = """{
  "version":"1.0",
  "authorization-rules":{
    "sub":"NVIDIA-GPU-ATTESTATION",
    "secboot":true,
    "x-nvidia-gpu-manufacturer":"NVIDIA Corporation",
    "x-nvidia-attestation-type":"GPU",
    "x-nvidia-attestation-detailed-result":{
      "x-nvidia-gpu-driver-rim-schema-validated":true,
      "x-nvidia-gpu-vbios-rim-cert-validated":true,
      "x-nvidia-gpu-attestation-report-cert-chain-validated":true,
      "x-nvidia-gpu-driver-rim-schema-fetched":true,
      "x-nvidia-gpu-attestation-report-parsed":true,
      "x-nvidia-gpu-nonce-match":true,
      "x-nvidia-gpu-vbios-rim-signature-verified":true,
      "x-nvidia-gpu-driver-rim-signature-verified":true,
      "x-nvidia-gpu-arch-check":true,
      "x-nvidia-gpu-measurements-match":true,
      "x-nvidia-gpu-attestation-report-signature-verified":true,
      "x-nvidia-gpu-vbios-rim-schema-validated":true,
      "x-nvidia-gpu-driver-rim-cert-validated":true,
      "x-nvidia-gpu-vbios-rim-schema-fetched":true,
      "x-nvidia-gpu-vbios-rim-measurements-available":true,
      "x-nvidia-gpu-driver-rim-driver-measurements-available":true
    },
    "x-nvidia-gpu-driver-version":"535.104.05",
    "hwmodel":"GH100 A01 GSP BROM",
    "measres":"comparison-successful",
    "x-nvidia-gpu-vbios-version":"96.00.5E.00.02"
  }
}
"""
class GPUAuthorizer(CCAuthorizer):
    def __init__(self, verifier_url="https://nras.attestation.nvidia.com/v1/attest/gpu"):
        self.can_generate = True
        self.client = attestation.Attestation()
        self.client.set_name("thisNode1")
        self.client.set_nonce("931d8dd0add203ac3d8b4fbde75e115278eefcdceac5b87671a748f32364dfcb")
        self.client.add_verifier(attestation.Devices.GPU, attestation.Environment.REMOTE, verifier_url, "")
        self.remote_att_result_policy = json.dumps(policy)

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

if __name__=="__main__":
    gpu_ath = GPUAuthorizer(verifier_url="https://nras.attestation.nvidia.com/v1/attest/gpu")
    # gpu_tp.generate()
    # test_token = gpu_ath.generate()
    result = gpu_ath.verify(test_token)
    print(f"{result=}")

