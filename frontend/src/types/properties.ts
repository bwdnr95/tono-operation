// src/types/properties.ts
/**
 * Property Profile, Property Groups & OTA Mapping 타입 정의
 */

// 주소 노출 정책
export type AddressDisclosurePolicy = "always" | "checkin_day";

// ============================================================
// Property Group (숙소 그룹)
// ============================================================

export interface PropertyGroup {
  id: number;
  group_code: string;
  name: string;
  locale: string;

  // 체크인/체크아웃
  checkin_from?: string;
  checkout_until?: string;
  checkin_method?: string;

  // 위치/주소
  address_full?: string;
  address_summary?: string;
  address_disclosure_policy?: AddressDisclosurePolicy;
  location_guide?: string;
  access_guide?: string;

  // 공간/구조
  floor_plan?: string;
  bedroom_count?: number;
  bed_count?: number;
  bed_types?: string;
  bathroom_count?: number;
  has_elevator?: boolean;
  capacity_base?: number;
  capacity_max?: number;
  has_terrace?: boolean;

  // 네트워크/편의
  wifi_ssid?: string;
  wifi_password?: string;
  towel_count_provided?: number;
  aircon_count?: number;
  aircon_usage_guide?: string;
  heating_usage_guide?: string;

  // 추가 침구
  extra_bedding_available?: boolean;
  extra_bedding_price_info?: string;

  // 세탁/조리
  laundry_guide?: string;
  has_washer?: boolean;
  has_dryer?: boolean;
  cooking_allowed?: boolean;
  has_seasonings?: boolean;
  has_tableware?: boolean;
  has_rice_cooker?: boolean;

  // 엔터테인먼트
  has_tv?: boolean;
  has_projector?: boolean;
  has_turntable?: boolean;
  has_wine_opener?: boolean;

  // 수영장/바베큐
  has_pool?: boolean;
  hot_pool_fee_info?: string;  // Deprecated: 하위 호환용
  pool_fee?: string;
  pool_reservation_notice?: string;
  pool_payment_account?: string;
  bbq_available?: boolean;
  bbq_guide?: string;  // Deprecated: 하위 호환용
  bbq_fee?: string;
  bbq_reservation_notice?: string;
  bbq_payment_account?: string;

  // 정책
  parking_info?: string;
  pet_allowed?: boolean;
  pet_policy?: string;
  smoking_policy?: string;
  noise_policy?: string;
  house_rules?: string;
  space_overview?: string;

  // JSON 필드
  amenities?: Record<string, any>;
  extra_metadata?: Record<string, any>;
  faq_entries?: FaqEntry[];

  // 공통
  is_active: boolean;
  created_at: string;
  updated_at: string;
  property_count?: number; // 소속 property 수
}

export interface PropertyGroupListItem {
  id: number;
  group_code: string;
  name: string;
  is_active: boolean;
  property_count: number;
}

export type PropertyGroupCreate = Omit<PropertyGroup, "id" | "created_at" | "updated_at" | "property_count">;
export type PropertyGroupUpdate = Partial<PropertyGroupCreate>;

// ============================================================
// Property Profile (개별 숙소/객실)
// ============================================================

export interface PropertyProfile {
  id: number;
  property_code: string;
  group_code?: string; // 🆕 소속 그룹 코드
  name: string;
  locale: string;

  // 체크인/체크아웃
  checkin_from?: string;
  checkout_until?: string;
  checkin_method?: string;

  // 위치/주소
  address_full?: string;
  address_summary?: string;
  location_guide?: string;
  access_guide?: string;
  
  // 🆕 주소 노출 정책
  address_disclosure_policy?: AddressDisclosurePolicy;

  // 공간/구조
  floor_plan?: string;
  bedroom_count?: number;
  bed_count?: number;
  bed_types?: string;
  bathroom_count?: number;
  has_elevator?: boolean;
  capacity_base?: number;
  capacity_max?: number;
  has_terrace?: boolean;

  // 네트워크/편의
  wifi_ssid?: string;
  wifi_password?: string;
  towel_count_provided?: number;
  aircon_count?: number;
  aircon_usage_guide?: string;
  heating_usage_guide?: string;

  // 추가 침구
  extra_bedding_available?: boolean;
  extra_bedding_price_info?: string;

  // 세탁/조리
  laundry_guide?: string;
  has_washer?: boolean;
  has_dryer?: boolean;
  cooking_allowed?: boolean;
  has_seasonings?: boolean;
  has_tableware?: boolean;
  has_rice_cooker?: boolean;

  // 엔터테인먼트
  has_tv?: boolean;
  has_projector?: boolean;
  has_turntable?: boolean;
  has_wine_opener?: boolean;

  // 수영장/바베큐
  has_pool?: boolean;
  hot_pool_fee_info?: string;  // Deprecated: 하위 호환용
  pool_fee?: string;
  pool_reservation_notice?: string;
  pool_payment_account?: string;
  bbq_available?: boolean;
  bbq_guide?: string;  // Deprecated: 하위 호환용
  bbq_fee?: string;
  bbq_reservation_notice?: string;
  bbq_payment_account?: string;

  // 정책
  parking_info?: string;
  pet_allowed?: boolean;
  pet_policy?: string;
  smoking_policy?: string;
  noise_policy?: string;
  house_rules?: string;
  space_overview?: string;

  // JSON 필드
  amenities?: Record<string, any>;
  extra_metadata?: Record<string, any>;
  faq_entries?: FaqEntry[];

  // iCal
  ical_url?: string;
  ical_last_synced_at?: string;

  // 공통
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FaqEntry {
  key: string;
  category?: string;
  answer: string;
  pack_key?: string;  // 🆕 Answer Pack key
}

export type PropertyProfileCreate = Omit<PropertyProfile, "id" | "created_at" | "updated_at">;
export type PropertyProfileUpdate = Partial<PropertyProfileCreate>;

// OTA Mapping
export interface OtaMapping {
  id: number;
  ota: string;
  listing_id: string;
  listing_name?: string;
  property_code?: string; // 그룹 매핑 시 NULL 가능
  group_code?: string; // 🆕 그룹 매핑용
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OtaMappingCreate {
  ota?: string;
  listing_id: string;
  listing_name?: string;
  property_code?: string;
  group_code?: string;
}

// OTA 매핑 대상 (그룹 또는 숙소)
export interface MappingTarget {
  type: "group" | "property";
  code: string;
  name: string;
  group_code?: string; // property인 경우 소속 그룹
}
