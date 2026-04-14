from pydantic import BaseModel, ConfigDict


class Segment(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    name: str


class SegmentSummary(BaseModel):
    model_config = ConfigDict(extra="allow")
    vlan_id: int
    vni: int
    ip_range: str


class ACL(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    protocol: str
    src_address: str
    src_mask: str
    src_port: str
    dst_address: str
    dst_mask: str
    dst_port: str


class ACLCreateRequest(BaseModel):
    protocol: str
    src_address: str
    src_mask: str
    src_port: str
    dst_address: str
    dst_mask: str
    dst_port: str
    segment: str


class ACLUpdateRequest(BaseModel):
    protocol: str
    src_address: str
    src_mask: str
    src_port: str
    dst_address: str
    dst_mask: str
    dst_port: str


class DNAT(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    pool_address: str
    segment: str
    dst_address: str


class DNATRequest(BaseModel):
    pool_address: str
    segment: str
    dst_address: str
