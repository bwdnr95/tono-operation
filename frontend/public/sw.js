// public/sw.js
// Service Worker for TONO Push Notifications

const TONO_ICON = '/tono-icon.png';
const DEFAULT_URL = '/';

// Push 이벤트 수신
self.addEventListener('push', (event) => {
  console.log('[SW] Push received:', event);
  
  let data = {
    title: '🔔 TONO 알림',
    body: '새로운 알림이 있습니다.',
    icon: TONO_ICON,
    url: DEFAULT_URL,
    tag: 'tono-notification',
  };
  
  // 페이로드 파싱
  if (event.data) {
    try {
      data = { ...data, ...event.data.json() };
    } catch (e) {
      console.error('[SW] Failed to parse push data:', e);
    }
  }
  
  const options = {
    body: data.body,
    icon: data.icon || TONO_ICON,
    badge: '/tono-badge.png',
    tag: data.tag || 'tono-notification',
    renotify: true,  // 같은 tag라도 다시 알림
    requireInteraction: data.priority === 'high',  // high면 자동으로 안 사라짐
    data: {
      url: data.url || DEFAULT_URL,
      timestamp: data.timestamp,
    },
    // 진동 패턴 (모바일)
    vibrate: data.priority === 'high' ? [200, 100, 200, 100, 200] : [200, 100, 200],
    // 액션 버튼
    actions: [
      {
        action: 'open',
        title: '확인하기',
      },
      {
        action: 'dismiss',
        title: '닫기',
      },
    ],
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// 알림 클릭 이벤트
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked:', event);
  
  event.notification.close();
  
  // dismiss 액션이면 그냥 닫기
  if (event.action === 'dismiss') {
    return;
  }
  
  // URL 열기
  const urlToOpen = event.notification.data?.url || DEFAULT_URL;
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((windowClients) => {
        // 이미 열린 TONO 탭이 있으면 포커스
        for (const client of windowClients) {
          if (client.url.includes(self.location.origin)) {
            client.navigate(urlToOpen);
            return client.focus();
          }
        }
        // 없으면 새 탭 열기
        return clients.openWindow(urlToOpen);
      })
  );
});

// 알림 닫힘 이벤트 (선택적)
self.addEventListener('notificationclose', (event) => {
  console.log('[SW] Notification closed:', event);
});

// Service Worker 설치
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  self.skipWaiting();  // 즉시 활성화
});

// Service Worker 활성화
self.addEventListener('activate', (event) => {
  console.log('[SW] Activated');
  event.waitUntil(clients.claim());  // 모든 탭에서 즉시 제어
});
