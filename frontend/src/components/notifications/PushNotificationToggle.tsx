// src/components/notifications/PushNotificationToggle.tsx
/**
 * Push 알림 설정 토글 컴포넌트
 * 
 * 사용자가 브라우저 Push 알림을 켜고 끌 수 있는 UI
 */
import React, { useState, useEffect } from "react";
import {
  isPushSupported,
  getCurrentSubscription,
  createPushSubscription,
  cancelPushSubscription,
  sendTestPush,
} from "../../api/push";
import { useToast } from "../ui/Toast";

export default function PushNotificationToggle() {
  const [isSupported, setIsSupported] = useState(false);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [permission, setPermission] = useState<NotificationPermission>("default");
  const { showToast } = useToast();

  // 초기 상태 확인
  useEffect(() => {
    const checkStatus = async () => {
      const supported = isPushSupported();
      setIsSupported(supported);

      if (!supported) {
        setIsLoading(false);
        return;
      }

      // 현재 권한 상태
      if ("Notification" in window) {
        setPermission(Notification.permission);
      }

      // 현재 구독 상태
      const subscription = await getCurrentSubscription();
      setIsSubscribed(!!subscription);
      setIsLoading(false);
    };

    checkStatus();
  }, []);

  // Push 알림 켜기
  const handleEnable = async () => {
    setIsLoading(true);
    try {
      const subscription = await createPushSubscription();
      if (subscription) {
        setIsSubscribed(true);
        setPermission("granted");
        showToast({
          type: "success",
          title: "알림 켜짐",
          message: "브라우저 Push 알림이 활성화되었습니다.",
        });
      } else {
        showToast({
          type: "error",
          title: "알림 설정 실패",
          message: "알림 권한을 허용해주세요.",
        });
      }
    } catch (error) {
      console.error("Failed to enable push:", error);
      showToast({
        type: "error",
        title: "오류",
        message: "알림 설정 중 오류가 발생했습니다.",
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Push 알림 끄기
  const handleDisable = async () => {
    setIsLoading(true);
    try {
      await cancelPushSubscription();
      setIsSubscribed(false);
      showToast({
        type: "success",
        title: "알림 꺼짐",
        message: "브라우저 Push 알림이 비활성화되었습니다.",
      });
    } catch (error) {
      console.error("Failed to disable push:", error);
      showToast({
        type: "error",
        title: "오류",
        message: "알림 해제 중 오류가 발생했습니다.",
      });
    } finally {
      setIsLoading(false);
    }
  };

  // 테스트 알림 전송
  const handleTest = async () => {
    try {
      const result = await sendTestPush();
      if (result.success_count > 0) {
        showToast({
          type: "success",
          title: "테스트 알림 전송됨",
        });
      } else {
        showToast({
          type: "warning",
          title: "전송 실패",
          message: "활성 구독이 없거나 전송에 실패했습니다.",
        });
      }
    } catch (error) {
      showToast({
        type: "error",
        title: "오류",
        message: "테스트 알림 전송 실패",
      });
    }
  };

  // 지원하지 않는 브라우저
  if (!isSupported) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <span style={styles.icon}>🔔</span>
          <span style={styles.title}>브라우저 Push 알림</span>
        </div>
        <p style={styles.unsupportedText}>
          이 브라우저는 Push 알림을 지원하지 않습니다.
        </p>
      </div>
    );
  }

  // 권한이 거부된 경우
  if (permission === "denied") {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <span style={styles.icon}>🔔</span>
          <span style={styles.title}>브라우저 Push 알림</span>
        </div>
        <p style={styles.deniedText}>
          알림 권한이 차단되었습니다.
          <br />
          브라우저 설정에서 알림을 허용해주세요.
        </p>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.icon}>🔔</span>
        <span style={styles.title}>브라우저 Push 알림</span>
      </div>

      <p style={styles.description}>
        브라우저를 닫아도 긴급 알림을 받을 수 있습니다.
        <br />
        Safety Alert, 예약 요청, 미응답 경고 등
      </p>

      <div style={styles.actions}>
        {isSubscribed ? (
          <>
            <button
              onClick={handleDisable}
              disabled={isLoading}
              style={{ ...styles.button, ...styles.disableButton }}
            >
              {isLoading ? "처리 중..." : "알림 끄기"}
            </button>
            <button
              onClick={handleTest}
              disabled={isLoading}
              style={{ ...styles.button, ...styles.testButton }}
            >
              테스트
            </button>
          </>
        ) : (
          <button
            onClick={handleEnable}
            disabled={isLoading}
            style={{ ...styles.button, ...styles.enableButton }}
          >
            {isLoading ? "처리 중..." : "알림 켜기"}
          </button>
        )}
      </div>

      {isSubscribed && (
        <div style={styles.status}>
          <span style={styles.statusDot}>●</span>
          <span>Push 알림 활성화됨</span>
        </div>
      )}
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Styles
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: "16px",
    backgroundColor: "#f8fafc",
    borderRadius: "8px",
    border: "1px solid #e2e8f0",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginBottom: "12px",
  },
  icon: {
    fontSize: "20px",
  },
  title: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#1e293b",
  },
  description: {
    fontSize: "14px",
    color: "#64748b",
    lineHeight: 1.5,
    marginBottom: "16px",
  },
  actions: {
    display: "flex",
    gap: "8px",
  },
  button: {
    padding: "8px 16px",
    borderRadius: "6px",
    border: "none",
    fontSize: "14px",
    fontWeight: 500,
    cursor: "pointer",
    transition: "all 0.2s",
  },
  enableButton: {
    backgroundColor: "#3b82f6",
    color: "white",
  },
  disableButton: {
    backgroundColor: "#ef4444",
    color: "white",
  },
  testButton: {
    backgroundColor: "#6b7280",
    color: "white",
  },
  status: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    marginTop: "12px",
    fontSize: "13px",
    color: "#22c55e",
  },
  statusDot: {
    fontSize: "10px",
  },
  unsupportedText: {
    fontSize: "14px",
    color: "#94a3b8",
  },
  deniedText: {
    fontSize: "14px",
    color: "#ef4444",
    lineHeight: 1.5,
  },
};
