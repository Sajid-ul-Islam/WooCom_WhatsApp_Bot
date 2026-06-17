import os
import logging
import httpx
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class WhatsAppClient:
    def __init__(self):
        self.phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.token = os.getenv("WHATSAPP_ACCESS_TOKEN")

        if not self.phone_id or not self.token:
            logger.warning("WhatsApp Phone Number ID or Access Token not set in environment variables.")

        self.base_url = f"https://graph.facebook.com/v20.0/{self.phone_id}/messages"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _post_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Helper to send POST request to WhatsApp Cloud API."""
        if not self.phone_id or not self.token:
            logger.error("Cannot send message: WhatsApp configuration is missing.")
            return {"error": "Missing configuration"}

        try:
            response = await self._client.post(self.base_url, json=payload, headers=self.headers)
            response_data = response.json()
            if response.status_code != 200:
                logger.error(f"WhatsApp API Error status {response.status_code}: {response_data}")
            else:
                logger.info(f"WhatsApp message sent successfully: {response_data.get('messages', [{}])[0].get('id')}")
            return response_data
        except Exception as e:
            logger.error(f"Failed to post message to WhatsApp Cloud API: {e}")
            return {"error": str(e)}

    async def send_text_message(self, to: str, text: str) -> Dict[str, Any]:
        """Send a standard text message."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "body": text,
                "preview_url": True
            }
        }
        return await self._post_request(payload)

    async def send_reply_buttons(self, to: str, text: str, buttons: List[Dict[str, str]], header_text: Optional[str] = None, footer_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Send up to 3 interactive reply buttons.
        buttons format: [{"id": "button_id", "title": "Button Title"}, ...]
        """
        if not buttons:
            return await self.send_text_message(to, text)

        # Format buttons for Meta payload
        formatted_buttons = []
        for btn in buttons[:3]:  # WhatsApp limit is max 3 buttons
            formatted_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"][:20]  # Title limit is 20 characters
                }
            })

        interactive_payload: Dict[str, Any] = {
            "type": "button",
            "body": {
                "text": text
            },
            "action": {
                "buttons": formatted_buttons
            }
        }

        if header_text:
            interactive_payload["header"] = {
                "type": "text",
                "text": header_text[:60]  # Header limit is 60 characters
            }
        if footer_text:
            interactive_payload["footer"] = {
                "text": footer_text[:60]  # Footer limit is 60 characters
            }

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive_payload
        }
        return await self._post_request(payload)

    async def send_list_message(
        self,
        to: str,
        button_text: str,
        body_text: str,
        sections: List[Dict[str, Any]],
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an interactive list message (up to 10 rows total).
        sections format:
        [
            {
                "title": "Section Title",
                "rows": [
                    {"id": "row_id_1", "title": "Row Title 1", "description": "Optional Desc"},
                    ...
                ]
            }
        ]
        """
        # Truncate and clean section rows to fit limits
        clean_sections = []
        total_rows = 0

        for sec in sections:
            if total_rows >= 10:
                break

            sec_rows = []
            for row in sec.get("rows", []):
                if total_rows >= 10:
                    break
                sec_rows.append({
                    "id": row["id"],
                    "title": row["title"][:24],  # Title limit is 24 characters
                    "description": row.get("description", "")[:72]  # Description limit is 72 characters
                })
                total_rows += 1

            if sec_rows:
                clean_sections.append({
                    "title": sec.get("title", "Select")[:24],  # Section title limit is 24 characters
                    "rows": sec_rows
                })

        interactive_payload: Dict[str, Any] = {
            "type": "list",
            "body": {
                "text": body_text[:1024]  # Body limit is 1024 characters
            },
            "action": {
                "button": button_text[:20],  # Action button text limit is 20 characters
                "sections": clean_sections
            }
        }

        if header_text:
            interactive_payload["header"] = {
                "type": "text",
                "text": header_text[:60]
            }
        if footer_text:
            interactive_payload["footer"] = {
                "text": footer_text[:60]
            }

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive_payload
        }
        return await self._post_request(payload)

    async def send_image_message(self, to: str, image_url: str, caption: Optional[str] = None) -> Dict[str, Any]:
        """Send an image with an optional caption."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {
                "link": image_url
            }
        }
        if caption:
            payload["image"]["caption"] = caption[:1024]  # Caption limit is 1024 characters
        return await self._post_request(payload)
