// src/api/push.ts
/**
 * Push Notification API Client
 */
import { apiGet, apiPost } from "./client";

/**
 * VAPID 공개키 조회
 */
export async function getVapidPublicKey(): Promise<string> {
  const res = await apiGet<{ public_key: string }>("/push/vapid-public-key");
  return res.public_key;
}

/**
 * Push 구독 등록
 */
export async function subscribePush(subscription: PushSubscription): Promise<void> {
  const json = subscription.toJSON();
  await apiPost("/push/subscribe", {
    endpoint: json.endpoint,
    keys: json.keys,
  });
}

/**
 * Push 구독 해제
 */
export async function unsubscribePush(endpoint: string): Promise<void> {
  await apiPost("/push/unsubscribe", { endpoint });
}

/**
 * 테스트 Push 전송
 */
export async function sendTestPush(
  title?: string,
  body?: string,
  url?: string
): Promise<{ success_count: number; failure_count: number }> {
  return await apiPost("/push/test", { title, body, url });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Push 구독 유틸리티
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/**
 * Service Worker 등록
 */
export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) {
    console.warn("Service Worker not supported");
    return null;
  }

  try {
    const registration = await navigator.serviceWorker.register("/sw.js");
    console.log("Service Worker registered:", registration);
    return registration;
  } catch (error) {
    console.error("Service Worker registration failed:", error);
    return null;
  }
}

/**
 * Push 알림 권한 요청
 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!("Notification" in window)) {
    console.warn("Notifications not supported");
    return "denied";
  }

  const permission = await Notification.requestPermission();
  console.log("Notification permission:", permission);
  return permission;
}

/**
 * Push 구독 생성 및 서버 등록
 */
export async function createPushSubscription(): Promise<PushSubscription | null> {
  try {
    // 1. Service Worker 등록
    const registration = await registerServiceWorker();
    if (!registration) return null;

    // 2. 권한 요청
    const permission = await requestNotificationPermission();
    if (permission !== "granted") {
      console.warn("Notification permission denied");
      return null;
    }

    // 3. VAPID 공개키 가져오기
    const vapidPublicKey = await getVapidPublicKey();

    // 4. URL-safe base64 → Uint8Array
    const applicationServerKey = urlBase64ToUint8Array(vapidPublicKey);

    // 5. Push 구독 생성
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    });

    // 6. 서버에 구독 정보 저장
    await subscribePush(subscription);

    console.log("Push subscription created:", subscription);
    return subscription;
  } catch (error) {
    console.error("Failed to create push subscription:", error);
    return null;
  }
}

/**
 * 현재 Push 구독 상태 확인
 */
export async function getCurrentSubscription(): Promise<PushSubscription | null> {
  if (!("serviceWorker" in navigator)) return null;

  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    return subscription;
  } catch (error) {
    console.error("Failed to get current subscription:", error);
    return null;
  }
}

/**
 * Push 구독 취소
 */
export async function cancelPushSubscription(): Promise<boolean> {
  try {
    const subscription = await getCurrentSubscription();
    if (!subscription) return false;

    // 서버에서 구독 해제
    await unsubscribePush(subscription.endpoint);

    // 브라우저에서 구독 해제
    await subscription.unsubscribe();

    console.log("Push subscription cancelled");
    return true;
  } catch (error) {
    console.error("Failed to cancel push subscription:", error);
    return false;
  }
}

/**
 * Push 알림 지원 여부 확인
 */
export function isPushSupported(): boolean {
  return (
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/**
 * URL-safe base64 → Uint8Array 변환
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }

  return outputArray;
}
