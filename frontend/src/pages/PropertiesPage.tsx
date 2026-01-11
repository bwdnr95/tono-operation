// src/pages/PropertiesPage.tsx
/**
 * 숙소 관리 페이지
 * 
 * - PropertyProfile CRUD
 * - OTA Listing Mapping 연결
 */
import { useState, useEffect, useCallback } from "react";
import { PageLayout } from "../layout/PageLayout";
import { useToast } from "../components/ui/Toast";
import {
  getProperties,
  getProperty,
  createProperty as apiCreateProperty,
  updateProperty as apiUpdateProperty,
  getOtaMappings,
  createOtaMapping as apiCreateOtaMapping,
  deleteOtaMapping as apiDeleteOtaMapping,
} from "../api/properties";
import type {
  PropertyProfile,
  OtaMapping,
} from "../types/properties";

interface FormSectionProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function FormSection({ title, children, defaultOpen = false }: FormSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  
  return (
    <div className="card" style={{ marginBottom: "16px" }}>
      <div
        className="card-header"
        style={{ cursor: "pointer" }}
        onClick={() => setOpen(!open)}
      >
        <span className="card-title">{title}</span>
        <span style={{ fontSize: "18px" }}>{open ? "▼" : "▶"}</span>
      </div>
      {open && (
        <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
          {children}
        </div>
      )}
    </div>
  );
}

// Form Field Components

interface TextFieldProps {
  label: string;
  value: string | undefined;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
  multiline?: boolean;
}

function TextField({ label, value, onChange, placeholder, required, multiline }: TextFieldProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <label style={{ fontSize: "13px", fontWeight: "500", color: "var(--text-secondary)" }}>
        {label} {required && <span style={{ color: "var(--danger)" }}>*</span>}
      </label>
      {multiline ? (
        <textarea
          className="input"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          style={{ minHeight: "80px", resize: "vertical" }}
        />
      ) : (
        <input
          className="input"
          type="text"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
        />
      )}
    </div>
  );
}

interface NumberFieldProps {
  label: string;
  value: number | undefined;
  onChange: (v: number | undefined) => void;
  placeholder?: string;
}

function NumberField({ label, value, onChange, placeholder }: NumberFieldProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <label style={{ fontSize: "13px", fontWeight: "500", color: "var(--text-secondary)" }}>
        {label}
      </label>
      <input
        className="input"
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value ? parseInt(e.target.value) : undefined)}
        placeholder={placeholder}
      />
    </div>
  );
}

interface BooleanFieldProps {
  label: string;
  value: boolean | undefined;
  onChange: (v: boolean | undefined) => void;
}

function BooleanField({ label, value, onChange }: BooleanFieldProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <input
        type="checkbox"
        checked={value ?? false}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: "18px", height: "18px" }}
      />
      <label style={{ fontSize: "14px" }}>{label}</label>
    </div>
  );
}

interface SelectFieldProps {
  label: string;
  value: string | undefined;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  helpText?: string;
}

function SelectField({ label, value, onChange, options, helpText }: SelectFieldProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <label style={{ fontSize: "13px", fontWeight: "500", color: "var(--text-secondary)" }}>
        {label}
      </label>
      <select
        className="input"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        style={{ padding: "8px 12px" }}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {helpText && (
        <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          {helpText}
        </span>
      )}
    </div>
  );
}

// Property Form Component

interface PropertyFormProps {
  property?: PropertyProfile;
  onSave: (data: Partial<PropertyProfile>) => void;
  onCancel: () => void;
  saving: boolean;
}

function PropertyForm({ property, onSave, onCancel, saving }: PropertyFormProps) {
  const [form, setForm] = useState<Partial<PropertyProfile>>(property || {
    locale: "ko-KR",
    is_active: true,
  });
  
  const update = <K extends keyof PropertyProfile>(key: K, value: PropertyProfile[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(form);
  };
  
  return (
    <form onSubmit={handleSubmit}>
      {/* 기본 정보 */}
      <FormSection title="📋 기본 정보" defaultOpen={true}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <TextField
            label="숙소 코드"
            value={form.property_code}
            onChange={(v) => update("property_code", v)}
            placeholder="예: 2BS28"
            required
          />
          <TextField
            label="숙소 이름"
            value={form.name}
            onChange={(v) => update("name", v)}
            placeholder="예: 공감공간 공감스테이"
            required
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <TextField
            label="언어"
            value={form.locale}
            onChange={(v) => update("locale", v)}
            placeholder="ko-KR"
          />
          <BooleanField
            label="활성화"
            value={form.is_active}
            onChange={(v) => update("is_active", v ?? true)}
          />
        </div>
      </FormSection>
      
      {/* iCal 연동 */}
      <FormSection title="📅 iCal 연동">
        <TextField
          label="iCal URL"
          value={form.ical_url}
          onChange={(v) => update("ical_url", v)}
          placeholder="https://www.airbnb.co.kr/calendar/ical/xxxxx.ics?s=xxxxx"
        />
        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          Airbnb → 달력 → 달력 내보내기에서 iCal 링크를 복사하세요.
          <br />
          설정 후 달력 페이지에서 동기화하면 차단된 날짜가 표시됩니다.
        </div>
      </FormSection>
      
      {/* 체크인/체크아웃 */}
      <FormSection title="🕐 체크인/체크아웃">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "12px" }}>
          <TextField
            label="체크인 시간"
            value={form.checkin_from}
            onChange={(v) => update("checkin_from", v)}
            placeholder="15:00"
          />
          <TextField
            label="체크아웃 시간"
            value={form.checkout_until}
            onChange={(v) => update("checkout_until", v)}
            placeholder="11:00"
          />
          <TextField
            label="체크인 방식"
            value={form.checkin_method}
            onChange={(v) => update("checkin_method", v)}
            placeholder="DOORLOCK_SELF_CHECKIN"
          />
        </div>
      </FormSection>
      
      {/* 위치/주소 */}
      <FormSection title="📍 위치/주소">
        <TextField
          label="상세 주소"
          value={form.address_full}
          onChange={(v) => update("address_full", v)}
          placeholder="제주시 애월읍 ..."
        />
        <TextField
          label="주소 요약"
          value={form.address_summary}
          onChange={(v) => update("address_summary", v)}
          placeholder="애월읍 해안도로 인근"
        />
        <SelectField
          label="🔒 주소 노출 정책"
          value={form.address_disclosure_policy || "checkin_day"}
          onChange={(v) => update("address_disclosure_policy", v)}
          options={[
            { value: "checkin_day", label: "체크인 당일부터 노출 (기본값)" },
            { value: "always", label: "예약 확정 시점부터 노출" },
          ]}
          helpText="AI 자동응답 시 상세 주소를 언제부터 게스트에게 안내할지 설정합니다."
        />
        <TextField
          label="위치 안내"
          value={form.location_guide}
          onChange={(v) => update("location_guide", v)}
          multiline
          placeholder="주변 랜드마크, 찾아오는 방법 등"
        />
        <TextField
          label="입장 안내"
          value={form.access_guide}
          onChange={(v) => update("access_guide", v)}
          multiline
          placeholder="현관문 비밀번호, 주차 위치 등"
        />
      </FormSection>
      
      {/* 공간/구조 */}
      <FormSection title="🏠 공간/구조">
        <TextField
          label="구조 설명"
          value={form.floor_plan}
          onChange={(v) => update("floor_plan", v)}
          multiline
          placeholder="복층 구조, 1층 거실+침실, 2층 침실..."
        />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" }}>
          <NumberField
            label="침실 수"
            value={form.bedroom_count}
            onChange={(v) => update("bedroom_count", v)}
          />
          <NumberField
            label="침대 수"
            value={form.bed_count}
            onChange={(v) => update("bed_count", v)}
          />
          <NumberField
            label="화장실 수"
            value={form.bathroom_count}
            onChange={(v) => update("bathroom_count", v)}
          />
          <NumberField
            label="기준 인원"
            value={form.capacity_base}
            onChange={(v) => update("capacity_base", v)}
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" }}>
          <NumberField
            label="최대 인원"
            value={form.capacity_max}
            onChange={(v) => update("capacity_max", v)}
          />
          <div></div>
          <BooleanField
            label="엘리베이터"
            value={form.has_elevator}
            onChange={(v) => update("has_elevator", v)}
          />
          <BooleanField
            label="테라스"
            value={form.has_terrace}
            onChange={(v) => update("has_terrace", v)}
          />
        </div>
        <TextField
          label="침대 타입"
          value={form.bed_types}
          onChange={(v) => update("bed_types", v)}
          placeholder="퀸 2개, 싱글 1개"
        />
      </FormSection>
      
      {/* 네트워크/편의 */}
      <FormSection title="📶 네트워크/편의시설">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <TextField
            label="WiFi SSID"
            value={form.wifi_ssid}
            onChange={(v) => update("wifi_ssid", v)}
          />
          <TextField
            label="WiFi 비밀번호"
            value={form.wifi_password}
            onChange={(v) => update("wifi_password", v)}
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <NumberField
            label="제공 수건 수"
            value={form.towel_count_provided}
            onChange={(v) => update("towel_count_provided", v)}
          />
          <NumberField
            label="에어컨 수"
            value={form.aircon_count}
            onChange={(v) => update("aircon_count", v)}
          />
        </div>
        <TextField
          label="에어컨 사용 안내"
          value={form.aircon_usage_guide}
          onChange={(v) => update("aircon_usage_guide", v)}
          multiline
        />
        <TextField
          label="난방 사용 안내"
          value={form.heating_usage_guide}
          onChange={(v) => update("heating_usage_guide", v)}
          multiline
        />
      </FormSection>
      
      {/* 추가 침구 */}
      <FormSection title="🛏️ 추가 침구">
        <BooleanField
          label="추가 침구 제공 가능"
          value={form.extra_bedding_available}
          onChange={(v) => update("extra_bedding_available", v)}
        />
        <TextField
          label="추가 침구 요금 안내"
          value={form.extra_bedding_price_info}
          onChange={(v) => update("extra_bedding_price_info", v)}
          placeholder="1세트 10,000원"
        />
      </FormSection>
      
      {/* 세탁/조리 */}
      <FormSection title="🧺 세탁/조리">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" }}>
          <BooleanField
            label="세탁기"
            value={form.has_washer}
            onChange={(v) => update("has_washer", v)}
          />
          <BooleanField
            label="건조기"
            value={form.has_dryer}
            onChange={(v) => update("has_dryer", v)}
          />
          <BooleanField
            label="조리 가능"
            value={form.cooking_allowed}
            onChange={(v) => update("cooking_allowed", v)}
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" }}>
          <BooleanField
            label="양념류 제공"
            value={form.has_seasonings}
            onChange={(v) => update("has_seasonings", v)}
          />
          <BooleanField
            label="식기류 제공"
            value={form.has_tableware}
            onChange={(v) => update("has_tableware", v)}
          />
          <BooleanField
            label="밥솥"
            value={form.has_rice_cooker}
            onChange={(v) => update("has_rice_cooker", v)}
          />
        </div>
        <TextField
          label="세탁 안내"
          value={form.laundry_guide}
          onChange={(v) => update("laundry_guide", v)}
          multiline
        />
      </FormSection>
      
      {/* 엔터테인먼트 */}
      <FormSection title="🎬 엔터테인먼트">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" }}>
          <BooleanField
            label="TV"
            value={form.has_tv}
            onChange={(v) => update("has_tv", v)}
          />
          <BooleanField
            label="프로젝터"
            value={form.has_projector}
            onChange={(v) => update("has_projector", v)}
          />
          <BooleanField
            label="턴테이블"
            value={form.has_turntable}
            onChange={(v) => update("has_turntable", v)}
          />
          <BooleanField
            label="와인 오프너"
            value={form.has_wine_opener}
            onChange={(v) => update("has_wine_opener", v)}
          />
        </div>
      </FormSection>
      
      {/* 수영장/바베큐 */}
      <FormSection title="🏊 수영장/바베큐">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <BooleanField
            label="수영장"
            value={form.has_pool}
            onChange={(v) => update("has_pool", v)}
          />
          <BooleanField
            label="바베큐 가능"
            value={form.bbq_available}
            onChange={(v) => update("bbq_available", v)}
          />
        </div>
        
        {/* Pool 구조화 필드 */}
        {form.has_pool && (
          <div style={{ 
            marginLeft: "24px", 
            paddingLeft: "16px", 
            borderLeft: "2px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}>
            <TextField
              label="수영장/온수풀 이용료"
              value={form.pool_fee}
              onChange={(v) => update("pool_fee", v)}
              placeholder="예: 100,000원"
            />
            <TextField
              label="수영장 예약 안내"
              value={form.pool_reservation_notice}
              onChange={(v) => update("pool_reservation_notice", v)}
              placeholder="예: 최소 2일 전 예약 필요"
            />
            <TextField
              label="수영장 결제 계좌 ⭐"
              value={form.pool_payment_account}
              onChange={(v) => update("pool_payment_account", v)}
              placeholder="예: 카카오뱅크 79420372489 (송대섭)"
            />
          </div>
        )}
        
        {/* BBQ 구조화 필드 */}
        {form.bbq_available && (
          <div style={{ 
            marginLeft: "24px", 
            paddingLeft: "16px", 
            borderLeft: "2px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}>
            <TextField
              label="바베큐 이용료"
              value={form.bbq_fee}
              onChange={(v) => update("bbq_fee", v)}
              placeholder="예: 30,000원 또는 무료"
            />
            <TextField
              label="바베큐 예약/이용 안내"
              value={form.bbq_reservation_notice}
              onChange={(v) => update("bbq_reservation_notice", v)}
              placeholder="예: 최소 1일 전 예약 필요 / 숯과 그릴만 준비"
            />
            <TextField
              label="바베큐 결제 계좌 ⭐"
              value={form.bbq_payment_account}
              onChange={(v) => update("bbq_payment_account", v)}
              placeholder="예: 카카오뱅크 79420372489 (송대섭)"
            />
          </div>
        )}
        
        {/* Deprecated 필드 (기존 데이터 호환용, 접힘) */}
        <details style={{ marginTop: "12px" }}>
          <summary style={{ 
            cursor: "pointer", 
            color: "var(--text-muted)", 
            fontSize: "12px" 
          }}>
            ⚠️ 기존 형식 (Deprecated - 위 구조화된 필드 사용 권장)
          </summary>
          <div style={{ marginTop: "12px", opacity: 0.7 }}>
            <TextField
              label="온수풀 요금 안내 (기존)"
              value={form.hot_pool_fee_info}
              onChange={(v) => update("hot_pool_fee_info", v)}
              placeholder="온수풀 1회 50,000원"
            />
            <TextField
              label="바베큐 안내 (기존)"
              value={form.bbq_guide}
              onChange={(v) => update("bbq_guide", v)}
              multiline
            />
          </div>
        </details>
      </FormSection>
      
      {/* 정책 */}
      <FormSection title="📜 정책/하우스룰">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <BooleanField
            label="반려동물 허용"
            value={form.pet_allowed}
            onChange={(v) => update("pet_allowed", v)}
          />
        </div>
        <TextField
          label="주차 안내"
          value={form.parking_info}
          onChange={(v) => update("parking_info", v)}
          multiline
        />
        <TextField
          label="반려동물 정책"
          value={form.pet_policy}
          onChange={(v) => update("pet_policy", v)}
          multiline
        />
        <TextField
          label="흡연 정책"
          value={form.smoking_policy}
          onChange={(v) => update("smoking_policy", v)}
          multiline
        />
        <TextField
          label="소음 정책"
          value={form.noise_policy}
          onChange={(v) => update("noise_policy", v)}
          multiline
        />
        <TextField
          label="하우스룰"
          value={form.house_rules}
          onChange={(v) => update("house_rules", v)}
          multiline
        />
        <TextField
          label="공간 소개"
          value={form.space_overview}
          onChange={(v) => update("space_overview", v)}
          multiline
        />
      </FormSection>
      
      {/* 버튼 */}
      <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end", marginTop: "16px" }}>
        <button type="button" onClick={onCancel} className="btn btn-secondary">
          취소
        </button>
        <button type="submit" disabled={saving} className="btn btn-primary">
          {saving ? "저장 중..." : "저장"}
        </button>
      </div>
    </form>
  );
}

// OTA Mapping Component

interface OtaMappingEditorProps {
  propertyCode: string;
  mappings: OtaMapping[];
  onAdd: (data: Partial<OtaMapping>) => void;
  onDelete: (id: number) => void;
}

function OtaMappingEditor({ propertyCode, mappings, onAdd, onDelete }: OtaMappingEditorProps) {
  const [newMapping, setNewMapping] = useState({ ota: "airbnb", listing_id: "", listing_name: "" });
  
  const handleAdd = () => {
    if (!newMapping.listing_id) return;
    onAdd({
      ...newMapping,
      property_code: propertyCode,
    });
    setNewMapping({ ota: "airbnb", listing_id: "", listing_name: "" });
  };
  
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">🔗 OTA 리스팅 연결</span>
        <span className="badge badge-default">{mappings.length}</span>
      </div>
      <div style={{ padding: "16px" }}>
        {/* 기존 매핑 */}
        {mappings.length > 0 && (
          <div style={{ marginBottom: "16px" }}>
            {mappings.map((m) => (
              <div
                key={m.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "12px",
                  background: "var(--bg-secondary)",
                  borderRadius: "8px",
                  marginBottom: "8px",
                }}
              >
                <div>
                  <span className="badge badge-primary" style={{ marginRight: "8px" }}>
                    {m.ota}
                  </span>
                  <span style={{ fontWeight: "500" }}>{m.listing_id}</span>
                  {m.listing_name && (
                    <span style={{ color: "var(--text-muted)", marginLeft: "8px" }}>
                      {m.listing_name}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => onDelete(m.id)}
                  className="btn btn-ghost btn-sm"
                  style={{ color: "var(--danger)" }}
                >
                  삭제
                </button>
              </div>
            ))}
          </div>
        )}
        
        {/* 새 매핑 추가 */}
        <div style={{ display: "flex", gap: "8px", alignItems: "flex-end" }}>
          <div style={{ width: "100px" }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)" }}>OTA</label>
            <select
              className="select"
              value={newMapping.ota}
              onChange={(e) => setNewMapping({ ...newMapping, ota: e.target.value })}
            >
              <option value="airbnb">Airbnb</option>
              <option value="booking">Booking.com</option>
              <option value="agoda">Agoda</option>
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)" }}>Listing ID</label>
            <input
              className="input"
              placeholder="예: 1234567890"
              value={newMapping.listing_id}
              onChange={(e) => setNewMapping({ ...newMapping, listing_id: e.target.value })}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)" }}>이름 (선택)</label>
            <input
              className="input"
              placeholder="예: 공감스테이 101호"
              value={newMapping.listing_name}
              onChange={(e) => setNewMapping({ ...newMapping, listing_name: e.target.value })}
            />
          </div>
          <button onClick={handleAdd} className="btn btn-primary" disabled={!newMapping.listing_id}>
            추가
          </button>
        </div>
      </div>
    </div>
  );
}

// Main Page Component

export function PropertiesPage() {
  // State
  const [properties, setProperties] = useState<PropertyProfile[]>([]);
  const [selectedProperty, setSelectedProperty] = useState<PropertyProfile | null>(null);
  const [otaMappings, setOtaMappings] = useState<OtaMapping[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"list" | "create" | "edit">("list");
  
  const { showToast } = useToast();
  
  // Load properties
  const loadProperties = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getProperties();
      setProperties(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);
  
  useEffect(() => {
    loadProperties();
  }, [loadProperties]);
  
  // Load OTA mappings when property selected
  useEffect(() => {
    if (selectedProperty && mode === "edit") {
      getOtaMappings(selectedProperty.property_code)
        .then(setOtaMappings)
        .catch(() => setOtaMappings([]));
    }
  }, [selectedProperty, mode]);
  
  // Handlers
  const handleCreate = () => {
    setSelectedProperty(null);
    setOtaMappings([]);
    setMode("create");
  };
  
  const handleEdit = async (prop: PropertyProfile) => {
    setSelectedProperty(prop);
    setMode("edit");
  };
  
  const handleSave = async (data: Partial<PropertyProfile>) => {
    setSaving(true);
    setError(null);
    try {
      if (mode === "create") {
        const created = await apiCreateProperty(data);
        setSelectedProperty(created);
        setMode("edit");
        showToast({ type: "success", title: "숙소가 생성되었습니다." });
      } else {
        await apiUpdateProperty(data.property_code!, data);
        showToast({ type: "success", title: "저장되었습니다." });
      }
      await loadProperties();
    } catch (e: any) {
      setError(e.message);
      showToast({ type: "error", title: "저장 실패", message: e.message });
    } finally {
      setSaving(false);
    }
  };
  
  const handleCancel = () => {
    setSelectedProperty(null);
    setOtaMappings([]);
    setMode("list");
  };
  
  const handleAddOtaMapping = async (data: Partial<OtaMapping>) => {
    try {
      const created = await apiCreateOtaMapping(data);
      setOtaMappings((prev) => [...prev, created]);
      showToast({ type: "success", title: "리스팅 매핑이 추가되었습니다." });
    } catch (e: any) {
      setError(e.message);
      showToast({ type: "error", title: "매핑 추가 실패", message: e.message });
    }
  };
  
  const handleDeleteOtaMapping = async (id: number) => {
    try {
      await apiDeleteOtaMapping(id);
      setOtaMappings((prev) => prev.filter((m) => m.id !== id));
      showToast({ type: "success", title: "리스팅 매핑이 삭제되었습니다." });
    } catch (e: any) {
      setError(e.message);
      showToast({ type: "error", title: "매핑 삭제 실패", message: e.message });
    }
  };
  
  // Render
  return (
    <PageLayout>
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {/* Header */}
        <header className="page-header">
          <div className="page-header-content">
            <div>
              <h1 className="page-title">숙소 관리</h1>
              <p className="page-subtitle">Property Profile & OTA 리스팅 연결</p>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              {mode !== "list" && (
                <button onClick={handleCancel} className="btn btn-secondary">
                  ← 목록으로
                </button>
              )}
              {mode === "list" && (
                <>
                  <button onClick={loadProperties} disabled={loading} className="btn btn-secondary">
                    {loading ? "로딩..." : "새로고침"}
                  </button>
                  <button onClick={handleCreate} className="btn btn-primary">
                    + 새 숙소
                  </button>
                </>
              )}
            </div>
          </div>
        </header>
        
        {/* Error */}
        {error && (
          <div
            style={{
              background: "var(--danger-bg)",
              border: "1px solid var(--danger)",
              borderRadius: "var(--radius)",
              padding: "12px 16px",
              margin: "0 32px 16px",
              color: "var(--danger)",
            }}
          >
            {error}
          </div>
        )}
        
        {/* Content */}
        <div style={{ flex: 1, padding: "0 32px 32px", overflowY: "auto" }}>
          {mode === "list" && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">숙소 목록</span>
                <span className="badge badge-default">{properties.length}</span>
              </div>
              <div>
                {loading ? (
                  <div className="empty-state">
                    <div className="loading-spinner" />
                  </div>
                ) : properties.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-icon">🏠</div>
                    <div className="empty-state-title">등록된 숙소가 없습니다</div>
                    <div className="empty-state-text">새 숙소를 등록해보세요</div>
                  </div>
                ) : (
                  properties.map((prop) => (
                    <div
                      key={prop.id}
                      onClick={() => handleEdit(prop)}
                      className="conversation-item"
                    >
                      <div className="conversation-avatar">
                        {prop.name.charAt(0)}
                      </div>
                      <div className="conversation-content">
                        <div className="conversation-name">
                          {prop.name}
                          <span
                            className="badge badge-primary"
                            style={{ marginLeft: "8px", fontSize: "10px" }}
                          >
                            {prop.property_code}
                          </span>
                          {!prop.is_active && (
                            <span
                              className="badge badge-default"
                              style={{ marginLeft: "8px", fontSize: "10px" }}
                            >
                              비활성
                            </span>
                          )}
                        </div>
                        <div className="conversation-preview">
                          {prop.address_summary || prop.address_full || "주소 없음"}
                        </div>
                        <div className="conversation-meta">
                          <span className="badge badge-default">
                            {prop.bedroom_count || 0}침실
                          </span>
                          <span className="badge badge-default">
                            {prop.capacity_base || 0}~{prop.capacity_max || 0}인
                          </span>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
          
          {(mode === "create" || mode === "edit") && (
            <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
              <PropertyForm
                property={selectedProperty || undefined}
                onSave={handleSave}
                onCancel={handleCancel}
                saving={saving}
              />
              
              {mode === "edit" && selectedProperty && (
                <OtaMappingEditor
                  propertyCode={selectedProperty.property_code}
                  mappings={otaMappings}
                  onAdd={handleAddOtaMapping}
                  onDelete={handleDeleteOtaMapping}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
