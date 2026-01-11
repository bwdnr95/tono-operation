// src/api/properties.ts
/**
 * Property Profile, Property Groups & OTA Mapping API
 */
import { apiGet, apiPost, apiPut, apiDelete, apiPatch } from "./client";
import type {
  PropertyProfile,
  PropertyProfileCreate,
  PropertyProfileUpdate,
  PropertyGroup,
  PropertyGroupListItem,
  PropertyGroupCreate,
  PropertyGroupUpdate,
  OtaMapping,
  OtaMappingCreate,
  MappingTarget,
} from "../types/properties";

// ============================================================
// Property Group (별도 엔드포인트: /property-groups)
// ============================================================

/**
 * 숙소 그룹 목록 조회
 */
export function getPropertyGroups(params?: {
  is_active?: boolean;
}): Promise<PropertyGroupListItem[]> {
  return apiGet<PropertyGroupListItem[]>("/property-groups", params);
}

/**
 * 숙소 그룹 상세 조회
 */
export function getPropertyGroup(groupCode: string): Promise<PropertyGroup> {
  return apiGet<PropertyGroup>(`/property-groups/${groupCode}`);
}

/**
 * 숙소 그룹 생성
 */
export function createPropertyGroup(
  data: PropertyGroupCreate
): Promise<PropertyGroup> {
  return apiPost<PropertyGroup, PropertyGroupCreate>("/property-groups", data);
}

/**
 * 숙소 그룹 수정
 */
export function updatePropertyGroup(
  groupCode: string,
  data: PropertyGroupUpdate
): Promise<PropertyGroup> {
  return apiPut<PropertyGroup, PropertyGroupUpdate>(
    `/property-groups/${groupCode}`,
    data
  );
}

/**
 * 숙소 그룹 삭제 (soft delete)
 */
export function deletePropertyGroup(groupCode: string): Promise<void> {
  return apiDelete(`/property-groups/${groupCode}`);
}

/**
 * 그룹 내 숙소 목록
 */
export function getPropertiesInGroup(
  groupCode: string,
  params?: { is_active?: boolean }
): Promise<PropertyProfile[]> {
  return apiGet<PropertyProfile[]>(`/property-groups/${groupCode}/properties`, params);
}

/**
 * 숙소를 그룹에 추가
 */
export function addPropertyToGroup(
  groupCode: string,
  propertyCode: string
): Promise<{ message: string }> {
  return apiPost<{ message: string }, undefined>(
    `/property-groups/${groupCode}/properties/${propertyCode}`,
    undefined
  );
}

/**
 * 숙소를 그룹에서 제거
 */
export function removePropertyFromGroup(
  groupCode: string,
  propertyCode: string
): Promise<{ message: string }> {
  return apiDelete(`/property-groups/${groupCode}/properties/${propertyCode}`);
}

/**
 * OTA 매핑 선택용 - 그룹 + 숙소 통합 목록
 */
export function getMappingTargets(): Promise<MappingTarget[]> {
  return apiGet<MappingTarget[]>("/properties/mapping-targets");
}

// ============================================================
// Property Profile
// ============================================================

/**
 * 숙소 목록 조회
 */
export function getProperties(params?: {
  is_active?: boolean;
}): Promise<PropertyProfile[]> {
  return apiGet<PropertyProfile[]>("/properties", params);
}

/**
 * 숙소 상세 조회
 */
export function getProperty(propertyCode: string): Promise<PropertyProfile> {
  return apiGet<PropertyProfile>(`/properties/${propertyCode}`);
}

/**
 * 숙소 생성
 */
export function createProperty(
  data: PropertyProfileCreate
): Promise<PropertyProfile> {
  return apiPost<PropertyProfile, PropertyProfileCreate>("/properties", data);
}

/**
 * 숙소 수정
 */
export function updateProperty(
  propertyCode: string,
  data: PropertyProfileUpdate
): Promise<PropertyProfile> {
  return apiPut<PropertyProfile, PropertyProfileUpdate>(
    `/properties/${propertyCode}`,
    data
  );
}

/**
 * 숙소 삭제 (soft delete)
 */
export function deleteProperty(propertyCode: string): Promise<void> {
  return apiDelete(`/properties/${propertyCode}`);
}

// ============================================================
// OTA Mapping
// ============================================================

/**
 * 특정 숙소의 OTA 매핑 목록
 */
export function getOtaMappings(propertyCode: string): Promise<OtaMapping[]> {
  return apiGet<OtaMapping[]>(`/properties/${propertyCode}/ota-mappings`);
}

/**
 * OTA 매핑 생성
 */
export function createOtaMapping(data: OtaMappingCreate): Promise<OtaMapping> {
  return apiPost<OtaMapping, OtaMappingCreate>("/properties/ota-mappings", data);
}

/**
 * OTA 매핑 삭제
 */
export function deleteOtaMapping(mappingId: number): Promise<void> {
  return apiDelete(`/properties/ota-mappings/${mappingId}`);
}
