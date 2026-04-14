from pydantic import ValidationError
import pytest

from mdx_cli.models.network import (
    ACL,
    ACLCreateRequest,
    ACLUpdateRequest,
    DNAT,
    DNATRequest,
)


class TestACL:
    def test_acl_full_fields(self):
        acl = ACL(
            uuid="acl-1",
            protocol="TCP",
            src_address="0.0.0.0",
            src_mask="24",
            src_port="Any",
            dst_address="10.0.1.0",
            dst_mask="21",
            dst_port="Any",
        )
        assert acl.uuid == "acl-1"
        assert acl.protocol == "TCP"
        assert acl.src_address == "0.0.0.0"
        assert acl.src_mask == "24"
        assert acl.src_port == "Any"
        assert acl.dst_address == "10.0.1.0"
        assert acl.dst_mask == "21"
        assert acl.dst_port == "Any"


class TestACLCreateRequest:
    def test_create_request_includes_segment(self):
        req = ACLCreateRequest(
            protocol="TCP",
            src_address="0.0.0.0",
            src_mask="0",
            src_port="Any",
            dst_address="10.0.0.1",
            dst_mask="32",
            dst_port="22",
            segment="seg-uuid-1",
        )
        data = req.model_dump()
        assert data["segment"] == "seg-uuid-1"
        assert data["protocol"] == "TCP"


class TestACLUpdateRequest:
    def test_update_request_has_no_segment(self):
        req = ACLUpdateRequest(
            protocol="UDP",
            src_address="192.168.0.0",
            src_mask="16",
            src_port="Any",
            dst_address="10.0.0.1",
            dst_mask="32",
            dst_port="80",
        )
        data = req.model_dump()
        assert "segment" not in data
        assert data["protocol"] == "UDP"


class TestDNAT:
    def test_dnat_full_fields(self):
        dnat = DNAT(
            uuid="dnat-1",
            pool_address="203.0.113.10",
            segment="test-segment",
            dst_address="10.0.0.20",
        )
        assert dnat.uuid == "dnat-1"
        assert dnat.pool_address == "203.0.113.10"
        assert dnat.segment == "test-segment"
        assert dnat.dst_address == "10.0.0.20"


class TestDNATRequest:
    def test_dnat_request_fields(self):
        req = DNATRequest(
            pool_address="203.0.113.11",
            segment="seg-uuid-1",
            dst_address="10.0.0.1",
        )
        data = req.model_dump()
        assert data["pool_address"] == "203.0.113.11"
        assert data["segment"] == "seg-uuid-1"
        assert data["dst_address"] == "10.0.0.1"
