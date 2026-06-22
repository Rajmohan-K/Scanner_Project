"use client";
import dynamic from 'next/dynamic';
import Skeleton from '@/components/atoms/Skeleton';

const LazyStockGrid = dynamic(() => import('./StockGrid'), {
  ssr: false,
  loading: () => (
    <div className="stock-list-skeleton">
      {Array.from({ length: 8 }).map((_, index) => (
        <Skeleton key={index} width="100%" height={46} />
      ))}
    </div>
  ),
});

export default LazyStockGrid;
