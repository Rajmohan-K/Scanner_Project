"use client";

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function PremarketRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/scan-center?tab=premarket');
  }, [router]);

  return (
    <div style={{ padding: '40px', textAlign: 'center', fontFamily: 'var(--font-mono, monospace)', color: 'var(--muted)' }}>
      Redirecting to consolidated Stock Scanner (Premarket)...
    </div>
  );
}
