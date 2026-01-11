// src/hooks/useTheme.ts
/**
 * 다크/라이트 모드 테마 관리 훅
 * 
 * 사용법:
 *   const { theme, toggleTheme, setTheme } = useTheme();
 */
import { useState, useEffect, useCallback } from 'react';

export type Theme = 'light' | 'dark';

const THEME_KEY = 'tono-theme';

function getInitialTheme(): Theme {
  if (typeof window !== 'undefined') {
    // 1. localStorage에서 저장된 테마 확인
    const saved = localStorage.getItem(THEME_KEY) as Theme | null;
    if (saved === 'light' || saved === 'dark') {
      return saved;
    }
    
    // 2. 시스템 설정 확인
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
  }
  
  // 3. 기본값: light
  return 'light';
}

function applyTheme(theme: Theme) {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme);
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  // 초기 테마 적용
  useEffect(() => {
    applyTheme(theme);
  }, []);

  // 테마 변경
  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
    applyTheme(newTheme);
    localStorage.setItem(THEME_KEY, newTheme);
  }, []);

  // 토글
  const toggleTheme = useCallback(() => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
  }, [theme, setTheme]);

  // 시스템 테마 변경 감지
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    
    const handleChange = (e: MediaQueryListEvent) => {
      // localStorage에 저장된 값이 없을 때만 시스템 설정 따라감
      const saved = localStorage.getItem(THEME_KEY);
      if (!saved) {
        setTheme(e.matches ? 'dark' : 'light');
      }
    };
    
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [setTheme]);

  return {
    theme,
    setTheme,
    toggleTheme,
    isDark: theme === 'dark',
  };
}
