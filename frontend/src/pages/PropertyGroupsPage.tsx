// src/pages/PropertyGroupsPage.tsx
/**
 * 숙소 그룹 관리 페이지
 * 
 * - PropertyGroup CRUD
 * - 그룹에 숙소 추가/제거
 * - 그룹에 OTA 리스팅 매핑
 */
import { useState, useEffect, useCallback } from "react";
import { PageLayout } from "../layout/PageLayout";
import { useToast } from "../components/ui/Toast";
import {
  getPropertyGroups,
  getPropertyGroup,
  createPropertyGroup as apiCreateGroup,
  updatePropertyGroup as apiUpdateGroup,
  deletePropertyGroup as apiDeleteGroup,
  getPropertiesInGroup,
  getProperties,
  addPropertyToGroup,
  removePropertyFromGroup,
  createOtaMapping,
  deleteOtaMapping,
} from "../api/properties";
import { apiGet } from "../api/client";
import type {
  PropertyGroup,
  PropertyGroupListItem,
  PropertyProfile,
  OtaMapping,
} from "../types/properties";

// ============================================================
// Form Components
// ============================================================

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

// ============================================================
// Group Form
// ============================================================

interface GroupFormProps {
  group?: PropertyGroup;
  onSave: (data: Partial<PropertyGroup>) => void;
  onCancel: () => void;
  saving: boolean;
}

function GroupForm({ group, onSave, onCancel, saving }: GroupFormProps) {
  const [form, setForm] = useState<Partial<PropertyGroup>>(
    group || {
      locale: "ko-KR",
      is_active: true,
    }
  );

  const update = <K extends keyof PropertyGroup>(key: K, value: PropertyGroup[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(form);
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="card">
        <div className="card-header">
          <span className="card-title">📁 그룹 정보</span>
        </div>
        <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <TextField
              label="그룹 코드"
              value={form.group_code}
              onChange={(v) => update("group_code", v)}
              placeholder="예: 2S"
              required
            />
            <TextField
              label="그룹 이름"
              value={form.name}
              onChange={(v) => update("name", v)}
              placeholder="예: 솔레어 테라스"
              required
            />
          </div>

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

          <TextField
            label="주소"
            value={form.address_full}
            onChange={(v) => update("address_full", v)}
            placeholder="제주특별자치도 서귀포시..."
          />

          <TextField
            label="위치 안내"
            value={form.location_guide}
            onChange={(v) => update("location_guide", v)}
            placeholder="위치 및 찾아오는 방법"
            multiline
          />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <TextField
              label="WiFi SSID"
              value={form.wifi_ssid}
              onChange={(v) => update("wifi_ssid", v)}
              placeholder="WiFi 이름"
            />
            <TextField
              label="WiFi 비밀번호"
              value={form.wifi_password}
              onChange={(v) => update("wifi_password", v)}
              placeholder="WiFi 비밀번호"
            />
          </div>

          <TextField
            label="주차 안내"
            value={form.parking_info}
            onChange={(v) => update("parking_info", v)}
            placeholder="주차 관련 안내"
            multiline
          />

          <TextField
            label="하우스룰"
            value={form.house_rules}
            onChange={(v) => update("house_rules", v)}
            placeholder="공통 하우스룰"
            multiline
          />
          
          {/* 수영장/바베큐 섹션 */}
          <div style={{ 
            borderTop: "1px solid var(--border)", 
            paddingTop: "16px", 
            marginTop: "8px" 
          }}>
            <div style={{ 
              fontSize: "14px", 
              fontWeight: 600, 
              marginBottom: "12px",
              color: "var(--text-primary)"
            }}>
              🏊 수영장/바베큐
            </div>
            
            <div style={{ display: "flex", gap: "24px", marginBottom: "12px" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={form.has_pool ?? false}
                  onChange={(e) => update("has_pool", e.target.checked)}
                  style={{ width: "18px", height: "18px" }}
                />
                <span style={{ fontSize: "14px" }}>수영장/온수풀</span>
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={form.bbq_available ?? false}
                  onChange={(e) => update("bbq_available", e.target.checked)}
                  style={{ width: "18px", height: "18px" }}
                />
                <span style={{ fontSize: "14px" }}>바베큐 가능</span>
              </label>
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
                marginBottom: "16px",
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
                marginBottom: "16px",
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
          </div>
        </div>
      </div>

      {/* 버튼 */}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
        <button type="button" onClick={onCancel} className="btn btn-secondary" disabled={saving}>
          취소
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={saving || !form.group_code || !form.name}
        >
          {saving ? "저장 중..." : "저장"}
        </button>
      </div>
    </form>
  );
}

// ============================================================
// Group Properties Manager
// ============================================================

interface GroupPropertiesManagerProps {
  groupCode: string;
  groupName: string;
}

function GroupPropertiesManager({ groupCode, groupName }: GroupPropertiesManagerProps) {
  const [groupProperties, setGroupProperties] = useState<PropertyProfile[]>([]);
  const [allProperties, setAllProperties] = useState<PropertyProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    loadData();
  }, [groupCode]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [inGroup, all] = await Promise.all([
        getPropertiesInGroup(groupCode),
        getProperties({ is_active: true }),
      ]);
      setGroupProperties(inGroup);
      setAllProperties(all);
    } catch (e: any) {
      showToast({ type: "error", title: "로딩 실패", message: e.message });
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (propertyCode: string) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(propertyCode)) {
        next.delete(propertyCode);
      } else {
        next.add(propertyCode);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelectedCodes(new Set(availableProperties.map((p) => p.property_code)));
  };

  const clearSelection = () => {
    setSelectedCodes(new Set());
  };

  const handleAddSelected = async () => {
    if (selectedCodes.size === 0) return;

    setAdding(true);
    let successCount = 0;
    let failCount = 0;

    for (const code of selectedCodes) {
      try {
        await addPropertyToGroup(groupCode, code);
        successCount++;
      } catch (e) {
        failCount++;
      }
    }

    setAdding(false);
    setSelectedCodes(new Set());
    setShowAddModal(false);
    loadData();

    if (failCount === 0) {
      showToast({ type: "success", title: `${successCount}개 숙소가 추가되었습니다.` });
    } else {
      showToast({ 
        type: "warning", 
        title: `${successCount}개 성공, ${failCount}개 실패` 
      });
    }
  };

  const handleRemove = async (propertyCode: string) => {
    if (!confirm("이 숙소를 그룹에서 제거하시겠습니까?")) return;

    try {
      await removePropertyFromGroup(groupCode, propertyCode);
      showToast({ type: "success", title: "숙소가 그룹에서 제거되었습니다." });
      loadData();
    } catch (e: any) {
      showToast({ type: "error", title: "제거 실패", message: e.message });
    }
  };

  // 그룹에 없는 숙소들
  const availableProperties = allProperties.filter(
    (p) => !p.group_code || p.group_code !== groupCode
  );

  const openModal = () => {
    setSelectedCodes(new Set());
    setShowAddModal(true);
  };

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">🏠 그룹 소속 숙소</span>
        <button className="btn btn-primary btn-sm" onClick={openModal}>
          + 숙소 추가
        </button>
      </div>

      {loading ? (
        <div className="empty-state">
          <div className="loading-spinner" />
        </div>
      ) : groupProperties.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">🏠</div>
          <div className="empty-state-title">소속 숙소가 없습니다</div>
          <div className="empty-state-text">숙소를 추가해보세요</div>
        </div>
      ) : (
        <div>
          {groupProperties.map((prop) => (
            <div key={prop.id} className="conversation-item">
              <div className="conversation-avatar">{prop.name.charAt(0)}</div>
              <div className="conversation-content">
                <div className="conversation-name">
                  {prop.name}
                  <span
                    className="badge badge-primary"
                    style={{ marginLeft: "8px", fontSize: "10px" }}
                  >
                    {prop.property_code}
                  </span>
                </div>
                <div className="conversation-preview">
                  {prop.bed_types || "침대 정보 없음"} · 최대 {prop.capacity_max || "-"}인
                </div>
              </div>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => handleRemove(prop.property_code)}
                style={{ marginLeft: "auto" }}
              >
                제거
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 숙소 추가 모달 - 다중 선택 */}
      {showAddModal && (
        <div 
          className="modal-overlay" 
          onClick={() => setShowAddModal(false)}
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "var(--overlay)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            className="modal-content"
            onClick={(e) => e.stopPropagation()}
            style={{ 
              maxWidth: "520px",
              width: "90%",
              maxHeight: "80vh",
              background: "var(--surface)",
              borderRadius: "12px",
              boxShadow: "var(--shadow-lg)",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {/* Header */}
            <div style={{ 
              padding: "16px 20px", 
              borderBottom: "1px solid var(--border)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}>
              <h2 style={{ margin: 0, fontSize: "18px" }}>숙소 추가</h2>
              <button 
                onClick={() => setShowAddModal(false)}
                style={{
                  background: "none",
                  border: "none",
                  fontSize: "24px",
                  cursor: "pointer",
                  color: "var(--text-secondary)",
                }}
              >
                ×
              </button>
            </div>

            {/* Selection Controls */}
            {availableProperties.length > 0 && (
              <div style={{ 
                padding: "12px 20px", 
                borderBottom: "1px solid var(--border)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "var(--bg-secondary)",
              }}>
                <span style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
                  {selectedCodes.size > 0 
                    ? `${selectedCodes.size}개 선택됨` 
                    : `${availableProperties.length}개 숙소`}
                </span>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button 
                    className="btn btn-secondary btn-sm"
                    onClick={selectAll}
                    style={{ fontSize: "12px", padding: "4px 8px" }}
                  >
                    전체 선택
                  </button>
                  {selectedCodes.size > 0 && (
                    <button 
                      className="btn btn-secondary btn-sm"
                      onClick={clearSelection}
                      style={{ fontSize: "12px", padding: "4px 8px" }}
                    >
                      선택 해제
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Body */}
            <div style={{ 
              padding: "16px 20px", 
              overflowY: "auto",
              flex: 1,
            }}>
              {availableProperties.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-text">추가 가능한 숙소가 없습니다</div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {availableProperties.map((prop) => {
                    const isSelected = selectedCodes.has(prop.property_code);
                    return (
                      <div
                        key={prop.id}
                        onClick={() => toggleSelect(prop.property_code)}
                        style={{ 
                          cursor: "pointer",
                          padding: "12px",
                          borderRadius: "8px",
                          border: isSelected 
                            ? "2px solid var(--primary, #6366f1)" 
                            : "1px solid var(--border)",
                          background: isSelected 
                            ? "var(--primary-bg)" 
                            : "var(--surface)",
                          display: "flex",
                          alignItems: "center",
                          gap: "12px",
                          transition: "all 0.15s ease",
                        }}
                      >
                        {/* Checkbox */}
                        <div style={{
                          width: "20px",
                          height: "20px",
                          borderRadius: "4px",
                          border: isSelected 
                            ? "none" 
                            : "2px solid var(--border)",
                          background: isSelected 
                            ? "var(--primary, #6366f1)" 
                            : "transparent",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          flexShrink: 0,
                        }}>
                          {isSelected && (
                            <span style={{ color: "#fff", fontSize: "14px" }}>✓</span>
                          )}
                        </div>

                        {/* Avatar */}
                        <div 
                          className="conversation-avatar" 
                          style={{ 
                            width: "36px", 
                            height: "36px", 
                            fontSize: "14px",
                            flexShrink: 0,
                          }}
                        >
                          {prop.name.charAt(0)}
                        </div>

                        {/* Content */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 500, marginBottom: "2px" }}>
                            {prop.name}
                            <span
                              className="badge badge-default"
                              style={{ marginLeft: "8px", fontSize: "10px" }}
                            >
                              {prop.property_code}
                            </span>
                          </div>
                          {prop.group_code && (
                            <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                              현재: {prop.group_code} 소속
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Footer */}
            {availableProperties.length > 0 && (
              <div style={{ 
                padding: "16px 20px", 
                borderTop: "1px solid var(--border)",
                display: "flex",
                justifyContent: "flex-end",
                gap: "8px",
              }}>
                <button 
                  className="btn btn-secondary"
                  onClick={() => setShowAddModal(false)}
                  disabled={adding}
                >
                  취소
                </button>
                <button 
                  className="btn btn-primary"
                  onClick={handleAddSelected}
                  disabled={adding || selectedCodes.size === 0}
                >
                  {adding 
                    ? "추가 중..." 
                    : `${selectedCodes.size}개 추가`}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Group OTA Mapping Editor
// ============================================================

interface GroupOtaMappingEditorProps {
  groupCode: string;
}

function GroupOtaMappingEditor({ groupCode }: GroupOtaMappingEditorProps) {
  const [mappings, setMappings] = useState<OtaMapping[]>([]);
  const [loading, setLoading] = useState(true);
  const [newMapping, setNewMapping] = useState({
    ota: "airbnb",
    listing_id: "",
    listing_name: "",
  });
  const { showToast } = useToast();

  useEffect(() => {
    loadMappings();
  }, [groupCode]);

  const loadMappings = async () => {
    setLoading(true);
    try {
      // 그룹에 연결된 OTA 매핑 조회
      const all = await apiGet<OtaMapping[]>("/properties/all-ota-mappings");
      const groupMappings = all.filter((m) => m.group_code === groupCode && !m.property_code);
      setMappings(groupMappings);
    } catch (e: any) {
      showToast({ type: "error", title: "로딩 실패", message: e.message });
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async () => {
    if (!newMapping.listing_id.trim()) {
      showToast({ type: "error", title: "Listing ID를 입력해주세요." });
      return;
    }

    try {
      await createOtaMapping({
        ota: newMapping.ota,
        listing_id: newMapping.listing_id.trim(),
        listing_name: newMapping.listing_name.trim() || undefined,
        group_code: groupCode,
        // property_code는 NULL (그룹 매핑)
      });
      showToast({ type: "success", title: "OTA 리스팅이 연결되었습니다." });
      setNewMapping({ ota: "airbnb", listing_id: "", listing_name: "" });
      loadMappings();
    } catch (e: any) {
      showToast({ type: "error", title: "추가 실패", message: e.message });
    }
  };

  const handleDelete = async (mappingId: number) => {
    if (!confirm("이 OTA 리스팅 연결을 삭제하시겠습니까?")) return;

    try {
      await deleteOtaMapping(mappingId);
      showToast({ type: "success", title: "OTA 리스팅 연결이 삭제되었습니다." });
      loadMappings();
    } catch (e: any) {
      showToast({ type: "error", title: "삭제 실패", message: e.message });
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">🔗 OTA 리스팅 매핑</span>
        <span className="badge badge-default">{mappings.length}</span>
      </div>

      {loading ? (
        <div className="empty-state">
          <div className="loading-spinner" />
        </div>
      ) : (
        <>
          {/* 기존 매핑 목록 */}
          {mappings.length === 0 ? (
            <div className="empty-state" style={{ padding: "24px" }}>
              <div style={{ fontSize: "14px", color: "var(--text-muted)" }}>
                연결된 OTA 리스팅이 없습니다
              </div>
            </div>
          ) : (
            <div>
              {mappings.map((mapping) => (
                <div 
                  key={mapping.id} 
                  style={{ 
                    display: "flex", 
                    alignItems: "center", 
                    padding: "12px 16px",
                    borderBottom: "1px solid var(--border)",
                    gap: "12px",
                  }}
                >
                  <span 
                    className="badge badge-primary" 
                    style={{ textTransform: "uppercase", fontSize: "10px" }}
                  >
                    {mapping.ota}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 500 }}>
                      {mapping.listing_name || mapping.listing_id}
                    </div>
                    <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                      ID: {mapping.listing_id}
                    </div>
                  </div>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleDelete(mapping.id)}
                    style={{ color: "var(--danger)" }}
                  >
                    삭제
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* 새 매핑 추가 */}
          <div style={{ padding: "16px", borderTop: "1px solid var(--border)" }}>
            <div style={{ fontSize: "13px", fontWeight: 500, marginBottom: "12px" }}>
              새 리스팅 연결
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "flex-end", flexWrap: "wrap" }}>
              <div style={{ width: "100px" }}>
                <label style={{ fontSize: "12px", color: "var(--text-secondary)", display: "block", marginBottom: "4px" }}>
                  OTA
                </label>
                <select
                  className="input"
                  value={newMapping.ota}
                  onChange={(e) => setNewMapping({ ...newMapping, ota: e.target.value })}
                  style={{ padding: "8px" }}
                >
                  <option value="airbnb">Airbnb</option>
                  <option value="booking">Booking</option>
                  <option value="agoda">Agoda</option>
                </select>
              </div>
              <div style={{ flex: 1, minWidth: "150px" }}>
                <label style={{ fontSize: "12px", color: "var(--text-secondary)", display: "block", marginBottom: "4px" }}>
                  Listing ID *
                </label>
                <input
                  className="input"
                  placeholder="예: 1234567890"
                  value={newMapping.listing_id}
                  onChange={(e) => setNewMapping({ ...newMapping, listing_id: e.target.value })}
                />
              </div>
              <div style={{ flex: 1, minWidth: "150px" }}>
                <label style={{ fontSize: "12px", color: "var(--text-secondary)", display: "block", marginBottom: "4px" }}>
                  표시 이름
                </label>
                <input
                  className="input"
                  placeholder="예: 솔레어 테라스"
                  value={newMapping.listing_name}
                  onChange={(e) => setNewMapping({ ...newMapping, listing_name: e.target.value })}
                />
              </div>
              <button 
                className="btn btn-primary"
                onClick={handleAdd}
                disabled={!newMapping.listing_id.trim()}
              >
                추가
              </button>
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "8px" }}>
              그룹에 리스팅을 연결하면 예약이 들어왔을 때 객실 미배정 상태로 시작됩니다.
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================
// Main Page
// ============================================================

export function PropertyGroupsPage() {
  const [groups, setGroups] = useState<PropertyGroupListItem[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<PropertyGroup | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"list" | "create" | "edit">("list");

  const { showToast } = useToast();

  // Load groups
  const loadGroups = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPropertyGroups();
      setGroups(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  // Handlers
  const handleCreate = () => {
    setSelectedGroup(null);
    setMode("create");
  };

  const handleEdit = async (groupCode: string) => {
    try {
      const detail = await getPropertyGroup(groupCode);
      setSelectedGroup(detail);
      setMode("edit");
    } catch (e: any) {
      showToast({ type: "error", title: "로딩 실패", message: e.message });
    }
  };

  const handleSave = async (data: Partial<PropertyGroup>) => {
    setSaving(true);
    setError(null);
    try {
      if (mode === "create") {
        const created = await apiCreateGroup(data as any);
        setSelectedGroup(created);
        setMode("edit");
        showToast({ type: "success", title: "그룹이 생성되었습니다." });
      } else {
        await apiUpdateGroup(data.group_code!, data);
        showToast({ type: "success", title: "저장되었습니다." });
      }
      await loadGroups();
    } catch (e: any) {
      setError(e.message);
      showToast({ type: "error", title: "저장 실패", message: e.message });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (groupCode: string) => {
    if (!confirm("이 그룹을 삭제하시겠습니까?")) return;

    try {
      await apiDeleteGroup(groupCode);
      showToast({ type: "success", title: "그룹이 삭제되었습니다." });
      handleCancel();
      loadGroups();
    } catch (e: any) {
      showToast({ type: "error", title: "삭제 실패", message: e.message });
    }
  };

  const handleCancel = () => {
    setSelectedGroup(null);
    setMode("list");
  };

  return (
    <PageLayout>
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {/* Header */}
        <header className="page-header">
          <div className="page-header-content">
            <div>
              <h1 className="page-title">숙소 그룹 관리</h1>
              <p className="page-subtitle">호텔 객실타입, 숙소 그룹 관리</p>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              {mode !== "list" && (
                <button onClick={handleCancel} className="btn btn-secondary">
                  ← 목록으로
                </button>
              )}
              {mode === "list" && (
                <>
                  <button onClick={loadGroups} disabled={loading} className="btn btn-secondary">
                    {loading ? "로딩..." : "새로고침"}
                  </button>
                  <button onClick={handleCreate} className="btn btn-primary">
                    + 새 그룹
                  </button>
                </>
              )}
              {mode === "edit" && selectedGroup && (
                <button
                  onClick={() => handleDelete(selectedGroup.group_code)}
                  className="btn btn-secondary"
                  style={{ color: "var(--danger)" }}
                >
                  삭제
                </button>
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
                <span className="card-title">그룹 목록</span>
                <span className="badge badge-default">{groups.length}</span>
              </div>
              <div>
                {loading ? (
                  <div className="empty-state">
                    <div className="loading-spinner" />
                  </div>
                ) : groups.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-icon">📁</div>
                    <div className="empty-state-title">등록된 그룹이 없습니다</div>
                    <div className="empty-state-text">새 그룹을 등록해보세요</div>
                  </div>
                ) : (
                  groups.map((group) => (
                    <div
                      key={group.id}
                      onClick={() => handleEdit(group.group_code)}
                      className="conversation-item"
                    >
                      <div
                        className="conversation-avatar"
                        style={{ background: "var(--primary-bg)", color: "var(--primary)" }}
                      >
                        📁
                      </div>
                      <div className="conversation-content">
                        <div className="conversation-name">
                          {group.name}
                          <span
                            className="badge badge-primary"
                            style={{ marginLeft: "8px", fontSize: "10px" }}
                          >
                            {group.group_code}
                          </span>
                          {!group.is_active && (
                            <span
                              className="badge badge-default"
                              style={{ marginLeft: "8px", fontSize: "10px" }}
                            >
                              비활성
                            </span>
                          )}
                        </div>
                        <div className="conversation-preview">
                          소속 숙소 {group.property_count}개
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
              <GroupForm
                group={selectedGroup || undefined}
                onSave={handleSave}
                onCancel={handleCancel}
                saving={saving}
              />

              {mode === "edit" && selectedGroup && (
                <>
                  <GroupOtaMappingEditor
                    groupCode={selectedGroup.group_code}
                  />
                  <GroupPropertiesManager
                    groupCode={selectedGroup.group_code}
                    groupName={selectedGroup.name}
                  />
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
