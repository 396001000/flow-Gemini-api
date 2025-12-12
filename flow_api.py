import json
import time
import uuid
import os
import requests
import asyncio
from typing import Optional, List, Dict, Any, Union

class FlowClient:
    def __init__(self, cookies: Dict[str, str] = None):
        self.base_url = "https://aisandbox-pa.googleapis.com"
        self.api_key = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"  # Public key from logs
        self.tool_name = "PINHOLE"
        self.cookies = cookies or {}
        
        # Load cookies from file if not provided
        if not self.cookies:
            self.load_cookies()

        self.session = requests.Session()
        
        # 1. Construct Cookie String
        cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
        
        # 2. Extract CSRF Token (Next-Auth specific)
        # Format often: "token|hash" -> we need "token"
        csrf_token = None
        for k, v in self.cookies.items():
            if "csrf-token" in k:
                if "|" in v:
                    csrf_token = v.split("|")[0]
                else:
                    csrf_token = v
                break

        # 3. Build Headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            "Cookie": cookie_str,
            "x-goog-authuser": "0"  # Try default auth user
        }
        
        if csrf_token:
            headers["x-csrf-token"] = csrf_token
            headers["x-next-auth-csrf-token"] = csrf_token
            print(f"🔑 Extracted CSRF Token: {csrf_token[:10]}...")
            
        # 4. Load Bearer Token Override
        if os.path.exists("auth_token.json"):
            try:
                with open("auth_token.json", "r") as f:
                    auth_data = json.load(f)
                    if "Authorization" in auth_data:
                        headers["Authorization"] = auth_data["Authorization"]
                        print("🔑 Loaded Bearer Token from auth_token.json")
            except Exception as e:
                print(f"⚠️ Failed to load auth_token: {e}")

        self.session.headers.update(headers)

        self.project_id = None
        self.session_id = f";{int(time.time() * 1000)}"
        
        # Auto-validate
        self.validate_auth()

    def validate_auth(self):
        """Checks if the cookies are valid by fetching a simple resource."""
        try:
            # Using create_project as a test, or better, fetch user history which is read-only-ish
            print("🔍 Verifying API connection...")
            # We use fetchUserHistoryDirectly as it's a safe GET request used in polling
            url = "https://labs.google/fx/api/trpc/media.fetchUserHistoryDirectly"
            params = {
                "input": '{"json":{"type":"ASSET_MANAGER","pageSize":1,"responseScope":"RESPONSE_SCOPE_UNSPECIFIED","cursor":null},"meta":{"values":{"cursor":["undefined"]}}}'
            }
            resp = self.session.get(url, params=params)
            
            if resp.status_code == 200:
                print("✅ API Connection Verified! Cookies are valid.")
            elif resp.status_code == 401:
                print("❌ Authentication Failed (401). Your cookies might be expired or incomplete.")
                print("   👉 Please export ALL cookies from labs.google and update them.")
            else:
                print(f"⚠️ API Connection Warning: HTTP {resp.status_code}")
                # print(resp.text[:200])
        except Exception as e:
            print(f"⚠️ Validation skipped due to error: {e}")


    def load_cookies(self, path: str = "cookies.json"):
        """Load cookies from a JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                cookie_list = json.load(f)
                for cookie in cookie_list:
                    self.cookies[cookie['name']] = cookie['value']
            print(f"✅ Loaded {len(self.cookies)} cookies.")
        except Exception as e:
            print(f"⚠️ Failed to load cookies: {e}")

    def _get_client_context(self) -> Dict[str, Any]:
        """Returns the standard client context for requests."""
        if not self.project_id:
            # Try to create a project first if not set, or use a default/random one
            # For now, we'll try to create one or use a placeholder if creation fails
            try:
                self.create_project()
            except:
                print("⚠️ Project creation failed, using temporary ID")
                self.project_id = str(uuid.uuid4())

        return {
            "sessionId": self.session_id,
            "projectId": self.project_id,
            "tool": self.tool_name,
            "userPaygateTier": "PAYGATE_TIER_ONE"
        }

    def create_project(self, title: str = None) -> str:
        """Creates a new project and returns its ID."""
        if not title:
            title = f"Project - {int(time.time())}"
            
        url = "https://labs.google/fx/api/trpc/project.createProject"
        payload = {
            "json": {
                "projectTitle": title,
                "toolName": self.tool_name
            }
        }
        
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        
        self.project_id = data["result"]["data"]["json"]["result"]["projectId"]
        print(f"✅ Created project: {self.project_id}")
        return self.project_id

    def generate_video(
        self, 
        prompt: str, 
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE", 
        model: str = "veo_3_1_t2v_fast",
        count: int = 1,
        seed: int = None
    ) -> List[str]:
        """
        Generates a video from text.
        Returns a list of operation IDs (one per request).
        """
        url = f"{self.base_url}/v1/video:batchAsyncGenerateVideoText"
        
        requests_list = []
        for i in range(count):
            # Use different seeds for variation
            current_seed = (seed + i) if seed else int(time.time() * 1000 + i) % 2147483647
            
            requests_list.append({
                "aspectRatio": aspect_ratio,
                "seed": current_seed,
                "textInput": {
                    "prompt": prompt
                },
                "videoModelKey": model,
                "metadata": {
                    "sceneId": str(uuid.uuid4())
                }
            })

        payload = {
            "clientContext": self._get_client_context(),
            "requests": requests_list
        }

        print(f"🚀 Sending generation request... (Model: {model}, Count: {count})")
        resp = self.session.post(url, json=payload)
        
        if resp.status_code != 200:
            print(f"❌ Error: {resp.text}")
            resp.raise_for_status()

        data = resp.json()
        print(f"[GENERATE] Full response: {json.dumps(data, indent=2)[:1000]}...")
        
        ops = data.get("operations", [])
        # Return both operation IDs and the full response for debugging
        op_info = []
        for op in ops:
            info = {
                "name": op.get("operation", {}).get("name"),
                "sceneId": op.get("sceneId"),
                "status": op.get("status")
            }
            op_info.append(info)
            print(f"[GENERATE] Operation: {info}")
        
        return op_info if op_info else []

    def generate_video_from_image(
        self,
        start_image_id: str,
        prompt: str,
        end_image_id: str = None,
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        model: str = "veo_3_1_i2v_s_fast_fl",
        seed: int = None
    ) -> List[str]:
        """
        Generates a video from a start image (and optional end image).
        Note: image_id is the mediaId from uploaded assets (e.g. "CAMaJD...")
        """
        url = f"{self.base_url}/v1/video:batchAsyncGenerateVideoStartAndEndImage"
        
        if seed is None:
            seed = int(time.time() * 1000) % 2147483647

        req_data = {
            "aspectRatio": aspect_ratio,
            "seed": seed,
            "textInput": {"prompt": prompt},
            "videoModelKey": model,
            "startImage": {"mediaId": start_image_id},
            "metadata": {"sceneId": str(uuid.uuid4())}
        }

        if end_image_id:
            req_data["endImage"] = {"mediaId": end_image_id}

        payload = {
            "clientContext": self._get_client_context(),
            "requests": [req_data]
        }

        print(f"🚀 Sending image-to-video request... (Model: {model})")
        resp = self.session.post(url, json=payload)
        if resp.status_code != 200:
            print(f"❌ Error: {resp.text}")
            resp.raise_for_status()

        data = resp.json()
        ops = data.get("operations", [])
        return [op["operation"]["name"] for op in ops]

    def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE",
        model: str = "GEM_PIX_2",
        count: int = 4,
        seed: int = None
    ) -> Dict[str, Any]:
        """
        Generates images. Unlike video, this might return results immediately or a job ID.
        Based on logs, it returns a 'media' list directly if successful.
        """
        if not self.project_id:
            self._get_client_context() # Ensure project ID exists

        url = f"{self.base_url}/v1/projects/{self.project_id}/flowMedia:batchGenerateImages"
        
        requests_list = []
        for i in range(count):
            current_seed = (seed + i) if seed else int(time.time() * 1000 + i) % 2147483647
            requests_list.append({
                "clientContext": {
                    "sessionId": self.session_id,
                    "projectId": self.project_id,
                    "tool": self.tool_name
                },
                "seed": current_seed,
                "imageModelName": model,
                "imageAspectRatio": aspect_ratio,
                "prompt": prompt,
                "imageInputs": []
            })

        payload = {"requests": requests_list}

        print(f"🚀 Sending image generation request... (Count: {count})")
        print(f"[IMAGE API] Model: {model}, Ratio: {aspect_ratio}")
        resp = self.session.post(url, json=payload)
        if resp.status_code != 200:
            print(f"❌ Error: {resp.status_code}")
            # Save full error and request to file for debugging
            with open('image_error.txt', 'w', encoding='utf-8') as f:
                f.write(f"Status: {resp.status_code}\n")
                f.write(f"Response: {resp.text}\n")
                f.write(f"\n--- Request Payload ---\n")
                f.write(f"Model: {model}\n")
                f.write(f"Ratio: {aspect_ratio}\n")
                f.write(f"Count: {count}\n")
            print(f"❌ Full error saved to image_error.txt")
            resp.raise_for_status()

        return resp.json()

    def get_generation_result(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """
        Checks the status of an operation (media generation).
        The API seems to use the media ID to check status, but the operation ID 
        might be a temporary handle. 
        
        Actually, looking at the logs, the polling happens via:
        GET /v1/media/{mediaGenerationId}?key=...
        
        BUT, the initial response gives us an 'operation' name like "a13bd...".
        We need to transform this or wait for it.
        
        Wait! The operation name IS the ID we track. But where do we poll it?
        Usually Google APIs use /v1/operations/{name}, but the logs showed polling 
        /v1/media/{mediaGenerationId}.
        
        Looking closely at the logs:
        Response to generate: 
        "operations": [{"operation": {"name": "OP_ID"}, "sceneId": "...", "status": "PENDING"}]
        
        Then immediately:
        GET /v1/media/CAUSJ... (long base64-like ID)
        
        The 'mediaGenerationId' is NOT the operation ID. 
        We might need to fetch the operation status to GET the mediaGenerationId.
        
        However, in the logs, the `mediaGenerationId` appears in the `GET` request. 
        Where did the client get it?
        
        Ah, looking at the logs again...
        The `generate` response ONLY has `operation.name`.
        There must be an endpoint to check the operation status which returns the `mediaGenerationId`.
        
        Let's try to poll `/v1/operations/{name}` or similar if it exists (standard Google pattern).
        
        Actually, let's look at the logs again for "operations" in the URL.
        No grep results for "operations/" URL.
        
        Wait, I see "mediaGenerationId" in the GET request. 
        Maybe the operation name IS the mediaId?
        Let's check the format.
        Operation Name: "a13bd1b5a45cda8eb8124ef9629a023f" (Hex string)
        Media ID: "CAUSJDc3Mj..." (Base64 string)
        They are different.
        
        There MUST be a missing link. How does the client know the media ID?
        Maybe I missed a log entry or the client calculates it?
        Unlikely to calculate.
        
        Let's assume there is a `getOperation` or `listOperations` call I missed, OR
        maybe the `batchAsync` returns it in a field I missed?
        
        Let's look at the `batchAsync` response body again.
        
        ```json
        {
          "operations": [
            {
              "operation": {"name": "a13bd..."},
              "sceneId": "ba4c...",
              "status": "MEDIA_GENERATION_STATUS_PENDING"
            }
          ]
        }
        ```
        
        Nothing else.
        
        Hypothesis: The client polls `https://labs.google/fx/api/trpc/media.fetchUserHistory` or `media.get` using TRPC?
        
        Let's check the logs for `fetchUserHistory` or similar right after generation.
        Yes! Line 1177: `media.fetchUserHistoryDirectly`.
        And Line 1207 response contains `userWorkflows` with `mediaGenerationId`.
        
        So the flow is:
        1. Call Generate -> Get Operation ID (and implicit success)
        2. Poll `media.fetchUserHistoryDirectly` (or `fetchProjectWorkflows`) to see new items.
        3. Match the new item (maybe by time or just take the latest) to get `mediaGenerationId`.
        4. Poll `/v1/media/{mediaGenerationId}` for the actual URL.
        
        Let's implement `fetch_latest_media`.
        """
        pass

    def fetch_latest_workflow(self, project_id: str = None, media_type: str = "VIDEO") -> Optional[Dict[str, Any]]:
        """
        Fetches the latest workflow/media from history.
        
        Args:
            project_id: Optional project ID to filter by
            media_type: "VIDEO" uses PINHOLE, "IMAGE" uses ASSET_MANAGER
            
        Returns:
            The workflow dict containing 'name' (the media ID) and 'media' details
        """
        url = "https://labs.google/fx/api/trpc/media.fetchUserHistoryDirectly"
        
        # CRITICAL: Use "PINHOLE" for VIDEO history, "ASSET_MANAGER" for IMAGE
        type_param = "PINHOLE" if media_type == "VIDEO" else "ASSET_MANAGER"
        
        input_data = {
            "json": {
                "type": type_param,
                "pageSize": 10,  # Get more items to find our generation
                "responseScope": "RESPONSE_SCOPE_UNSPECIFIED",
                "cursor": None
            },
            "meta": {"values": {"cursor": ["undefined"]}}
        }
        
        params = {"input": json.dumps(input_data)}
        
        print(f"[HISTORY] Querying {type_param} history...")
        resp = self.session.get(url, params=params)
        
        if resp.status_code != 200:
            print(f"[HISTORY] ⚠️ Failed to fetch history: {resp.status_code}")
            return None
            
        try:
            data = resp.json()
            workflows = data.get("result", {}).get("data", {}).get("json", {}).get("result", {}).get("userWorkflows", [])
            print(f"[HISTORY] Found {len(workflows)} workflows")
            
            if not workflows:
                return None
            
            # If filtering by project, find matching workflow
            if project_id:
                for wf in workflows:
                    wf_pid = wf.get('media', {}).get('mediaGenerationId', {}).get('projectId')
                    if wf_pid == project_id:
                        media_id = wf.get('name', '')
                        print(f"[HISTORY] ✅ Found matching project! MediaID: {media_id[:40]}...")
                        return wf
                print(f"[HISTORY] No workflow matching projectId={project_id[:20]}...")
            
            # Return first workflow
            wf = workflows[0]
            media_id = wf.get('name', '')
            print(f"[HISTORY] First workflow MediaID: {media_id[:40]}...")
            return wf
                
        except Exception as e:
            print(f"[HISTORY] ⚠️ Error parsing history: {e}")
            import traceback
            traceback.print_exc()
            
        return None

    def fetch_workflows(self, project_id: str = None, media_type: str = "VIDEO", limit: int = 20) -> List[Dict]:
        """
        Fetches a list of recent user workflows.
        """
        url = "https://labs.google/fx/api/trpc/media.fetchUserHistoryDirectly"
        type_param = "PINHOLE" if media_type == "VIDEO" else "ASSET_MANAGER"
        
        input_data = {
            "json": {
                "type": type_param,
                "pageSize": limit,
                "responseScope": "RESPONSE_SCOPE_UNSPECIFIED",
                "cursor": None
            },
            "meta": {"values": {"cursor": ["undefined"]}}
        }
        
        # Only include projectId if provided
        if project_id:
            input_data["json"]["projectId"] = project_id
        
        params = {"input": json.dumps(input_data)}
        try:
            resp = self.session.get(url, params=params)
            if resp.status_code != 200:
                print(f"[HISTORY] ⚠️ Failed: {resp.status_code}")
                return []
                
            data = resp.json()
            workflows = data.get("result", {}).get("data", {}).get("json", {}).get("result", {}).get("userWorkflows", [])
            
            # Filter by project_id if provided and not handled by API
            if project_id:
                filtered = []
                for wf in workflows:
                    wf_pid = wf.get('media', {}).get('mediaGenerationId', {}).get('projectId')
                    if wf_pid == project_id:
                        filtered.append(wf)
                return filtered
            
            return workflows
        except Exception as e:
            print(f"[HISTORY] Error: {e}")
            return []

    def get_video_status(self, media_generation_id: str) -> Dict[str, Any]:
        """
        Gets the status and URL of a specific media generation.
        """
        url = f"{self.base_url}/v1/media/{media_generation_id}"
        params = {
            "key": self.api_key,
            "clientContext.tool": self.tool_name,
            "returnUriOnly": "true"
        }
        
        resp = self.session.get(url, params=params)
        if resp.status_code != 200:
            return {"status": "ERROR", "error": resp.text}
            
        return resp.json()

    async def poll_for_completion(self, media_generation_id: str, timeout: int = 300) -> Dict[str, Any]:
        """
        Polls until the video is ready or fails.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.get_video_status(media_generation_id)
            
            # Check if video object exists and has URL
            if "video" in result:
                video_info = result["video"]
                if "fifeUrl" in video_info:
                    print("✅ Generation Complete!")
                    return video_info
            
            # If it's an image generation, it might be different structure (handled in generate_image mostly)
            # But the API for media/{id} returns consistent structure usually.
            
            # TODO: robust status checking. 
            # The API doesn't explicitly say "PENDING" in the GET /media response in the logs I saw?
            # Actually, I didn't see a "PENDING" response for GET /media in the logs snippet (it was 200 OK with URL).
            # It might return 404 or a different status if not ready.
            
            print("⏳ Waiting for generation...")
            await asyncio.sleep(5)
            
        return {"status": "TIMEOUT"}

# Test execution (optional, can be called from main)
if __name__ == "__main__":
    client = FlowClient()
    # Test project creation
    # pid = client.create_project()
