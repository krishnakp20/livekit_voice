"""LiveKit SIP trunk, dispatch rules, and room management."""

import json
import os
import uuid
from typing import Any, Optional

from livekit import api

from app.core.config import settings
from app.services.phone_utils import sip_participant_identity


def livekit_worker_agent_name() -> str:
    """Must match worker registration (LIVEKIT_AGENT_NAME)."""
    return (os.getenv("LIVEKIT_AGENT_NAME") or settings.LIVEKIT_AGENT_NAME or "vbots").strip()


class LiveKitService:
    def __init__(self) -> None:
        self._lkapi: api.LiveKitAPI | None = None

    @property
    def lkapi(self) -> api.LiveKitAPI:
        if self._lkapi is None:
            self._lkapi = api.LiveKitAPI(
                url=settings.LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://"),
                api_key=settings.LIVEKIT_API_KEY,
                api_secret=settings.LIVEKIT_API_SECRET,
            )
        return self._lkapi

    async def create_room(self, room_name: Optional[str] = None) -> str:
        name = room_name or f"call-{uuid.uuid4().hex[:12]}"
        await self.lkapi.room.create_room(api.CreateRoomRequest(name=name))
        return name

    async def create_room_with_agent(self, room_name: str, agent_metadata: dict[str, Any]) -> str:
        """Create room and dispatch AI worker (required for outbound / campaign dials)."""
        meta_json = json.dumps(agent_metadata)
        agent_name = livekit_worker_agent_name()
        await self.lkapi.room.create_room(
            api.CreateRoomRequest(
                name=room_name,
                metadata=meta_json,
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=agent_name,
                        metadata=meta_json,
                    )
                ],
            )
        )
        return room_name

    async def create_access_token(
        self,
        room_name: str,
        identity: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        token = api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        token.with_identity(identity).with_name(identity).with_grants(
            api.VideoGrants(room_join=True, room=room_name)
        )
        if metadata:
            token.with_metadata(json.dumps(metadata))
        return token.to_jwt()

    async def create_sip_trunk(
        self,
        name: str,
        inbound_addresses: list[str],
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
        allowed_addresses: Optional[list[str]] = None,
    ) -> str:
        """Create inbound SIP trunk in LiveKit. Returns trunk ID.

        inbound_addresses: your DID numbers this trunk handles, e.g. ["+918888888888"]
        allowed_addresses: restrict which carrier IPs may send SIP, e.g. ["192.168.10.5"]
        """
        trunk = api.SIPInboundTrunkInfo(
            name=name,
            numbers=inbound_addresses,
        )
        if auth_username and auth_password:
            trunk.auth_username = auth_username
            trunk.auth_password = auth_password
        if allowed_addresses:
            trunk.allowed_addresses.extend(allowed_addresses)

        request = api.CreateSIPInboundTrunkRequest(trunk=trunk)
        result = await self.lkapi.sip.create_sip_inbound_trunk(request)
        return result.sip_trunk_id

    async def create_outbound_sip_trunk(
        self,
        name: str,
        address: str,
        numbers: list[str],
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
    ) -> str:
        """Create outbound SIP trunk in LiveKit. Returns trunk ID.

        address: carrier/dialer SIP server, e.g. "192.168.10.5:5060"
        numbers: your caller ID numbers, e.g. ["+918888888888"]
        """
        trunk = api.SIPOutboundTrunkInfo(
            name=name,
            address=address,
            numbers=numbers,
        )
        if auth_username and auth_password:
            trunk.auth_username = auth_username
            trunk.auth_password = auth_password

        request = api.CreateSIPOutboundTrunkRequest(trunk=trunk)
        result = await self.lkapi.sip.create_sip_outbound_trunk(request)
        return result.sip_trunk_id

    def _room_config_with_agent(self, agent_metadata: dict[str, Any]) -> api.RoomConfiguration:
        """Attach AI worker to every SIP-created room (required for 'received job request')."""
        meta_json = json.dumps(agent_metadata)
        agent_name = livekit_worker_agent_name()
        return api.RoomConfiguration(
            metadata=meta_json,
            agents=[
                api.RoomAgentDispatch(
                    agent_name=agent_name,
                    metadata=meta_json,
                )
            ],
        )

    async def create_dispatch_rule(
        self,
        trunk_id: str,
        room_prefix: str,
        agent_metadata: dict[str, Any],
        inbound_numbers: list[str] | None = None,
    ) -> str:
        """Map inbound SIP to room and dispatch AI agent worker."""
        rule = api.SIPDispatchRule(
            dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                room_prefix=room_prefix,
            ),
        )
        request = api.CreateSIPDispatchRuleRequest(
            rule=rule,
            trunk_ids=[trunk_id],
            metadata=json.dumps(agent_metadata),
            room_config=self._room_config_with_agent(agent_metadata),
        )
        if inbound_numbers:
            request.inbound_numbers = inbound_numbers
        result = await self.lkapi.sip.create_sip_dispatch_rule(request)
        return result.sip_dispatch_rule_id

    async def delete_dispatch_rule(self, rule_id: str) -> None:
        await self.lkapi.sip.delete_dispatch_rule(
            api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
        )

    async def update_dispatch_rule_agent(
        self,
        existing: Any,
        agent_metadata: dict[str, Any],
    ) -> None:
        """Patch existing SIP dispatch rule to dispatch AI agent (preserves trunk_ids)."""
        rule_id = getattr(existing, "sip_dispatch_rule_id", None) or getattr(existing, "id", "")
        rule_obj = getattr(existing, "rule", None)
        if not rule_obj:
            rule_obj = api.SIPDispatchRule(
                dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix="call-"),
            )
        info = api.SIPDispatchRuleInfo(
            sip_dispatch_rule_id=rule_id,
            rule=rule_obj,
            trunk_ids=list(getattr(existing, "trunk_ids", []) or []),
            inbound_numbers=list(getattr(existing, "inbound_numbers", []) or []),
            metadata=json.dumps(agent_metadata),
            room_config=self._room_config_with_agent(agent_metadata),
        )
        if getattr(existing, "name", None):
            info.name = existing.name
        await self.lkapi.sip.update_dispatch_rule(rule_id, info)

    async def dial_participant(
        self,
        room_name: str,
        phone_number: str,
        trunk_id: str,
    ) -> str:
        """Outbound dial via SIP."""
        request = api.CreateSIPParticipantRequest(
            sip_trunk_id=trunk_id,
            sip_call_to=phone_number,
            room_name=room_name,
            participant_identity=sip_participant_identity(phone_number),
        )
        result = await self.lkapi.sip.create_sip_participant(request)
        return result.participant_id

    async def delete_room(self, room_name: str) -> None:
        await self.lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))

    async def list_inbound_trunks(self):
        """List SIP inbound trunks provisioned in LiveKit."""
        return await self.lkapi.sip.list_sip_inbound_trunk(api.ListSIPInboundTrunkRequest())

    async def list_outbound_trunks(self):
        return await self.lkapi.sip.list_sip_outbound_trunk(api.ListSIPOutboundTrunkRequest())

    async def list_dispatch_rules(self):
        """List SIP dispatch rules provisioned in LiveKit."""
        return await self.lkapi.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())


livekit_service = LiveKitService()
