// src/api/properties.ts
/**
 * Property Profile & OTA Mapping API
 */
import { apiGet, apiPost, apiPut, apiDelete } from "./client";
import type {
  PropertyProfile,
  PropertyProfileCreate,
  PropertyProfileUpdate,
  OtaMapping,
  OtaMappingCreate,
} from "../types/properties";

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
