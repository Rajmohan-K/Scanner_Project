"use client";

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function SwingRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/scan-center?tab=swing');
  }, [router]);

  return (
    <div style={{ padding: '40px', textAlign: 'center', fontFamily: 'var(--font-mono, monospace)', color: 'var(--muted)' }}>
      Redirecting to consolidated Stock Scanner (Swing)...
    </div>
  );
}
