import React from 'react';

export function Skeleton({ width = '100%', height = 16, style }: { width?: string | number; height?: number | string; style?: React.CSSProperties }) {
  return <div className="skeleton" style={{ width, height, ...style }} />;
}

export default Skeleton;
