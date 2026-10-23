import { useCallback, useEffect, useRef, useState } from 'react';
import type { CustomerOrder } from '../types';
import { supabase } from '../services/supabase';

export type OrderSyncState = 'connecting' | 'live' | 'reconnecting' | 'offline';
export type OrderChange = { kind: 'new' | 'status'; order: CustomerOrder; previousStatus?: string };

type Options = {
  loadOrders: () => Promise<CustomerOrder[]>;
  filter?: string;
  onChange?: (change: OrderChange) => void;
};

const statusSnapshot = (orders: CustomerOrder[]) => new Map(orders.map(order => [order.id, order.status]));

/**
 * Realtime events are deliberately treated as an invalidation signal only.
 * The existing authenticated API remains the authoritative source for cards,
 * order items, totals, and permission-scoped customer data.
 */
export function useRealtimeOrders({ loadOrders, filter, onChange }: Options) {
  const [orders, setOrders] = useState<CustomerOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [syncState, setSyncState] = useState<OrderSyncState>(supabase ? 'connecting' : 'offline');
  const snapshotRef = useRef<Map<string, string> | null>(null);
  const mountedRef = useRef(true);
  const syncStateRef = useRef<OrderSyncState>(supabase ? 'connecting' : 'offline');
  const refreshTimerRef = useRef<number | null>(null);

  const refresh = useCallback(async (initial = false) => {
    if (initial && mountedRef.current) setLoading(true);
    try {
      const next = await loadOrders();
      if (!mountedRef.current) return;
      const previous = snapshotRef.current;
      setOrders(next);
      setError('');
      snapshotRef.current = statusSnapshot(next);
      if (previous) {
        next.forEach(order => {
          const before = previous.get(order.id);
          if (!before) onChange?.({ kind: 'new', order });
          else if (before !== order.status) onChange?.({ kind: 'status', order, previousStatus: before });
        });
      }
    } catch (cause) {
      if (mountedRef.current) setError(cause instanceof Error ? cause.message : 'Unable to load orders.');
    } finally {
      if (mountedRef.current && initial) setLoading(false);
    }
  }, [loadOrders, onChange]);

  useEffect(() => {
    mountedRef.current = true;
    const setConnection = (next: OrderSyncState) => {
      syncStateRef.current = next;
      if (mountedRef.current) setSyncState(next);
    };
    const scheduleRefresh = () => {
      if (refreshTimerRef.current !== null) return;
      refreshTimerRef.current = window.setTimeout(() => {
        refreshTimerRef.current = null;
        if (document.visibilityState === 'visible') void refresh();
      }, 180);
    };

    void refresh(true);
    const client = supabase;
    if (!client) return () => { mountedRef.current = false; };

    const channel = client
      .channel(`orders-sync:${filter ?? 'staff'}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'orders', ...(filter ? { filter } : {}) }, scheduleRefresh)
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          setConnection('live');
          void refresh();
        } else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          setConnection('reconnecting');
        } else if (status === 'CLOSED') {
          setConnection('offline');
        }
      });
    const recover = () => {
      setConnection('reconnecting');
      if (document.visibilityState === 'visible') void refresh();
    };
    const onVisibility = () => {
      if (document.visibilityState === 'visible') recover();
    };
    window.addEventListener('online', recover);
    document.addEventListener('visibilitychange', onVisibility);
    const fallback = window.setInterval(() => {
      if (document.visibilityState === 'visible' && syncStateRef.current !== 'live') void refresh();
    }, 30_000);

    return () => {
      mountedRef.current = false;
      window.removeEventListener('online', recover);
      document.removeEventListener('visibilitychange', onVisibility);
      window.clearInterval(fallback);
      if (refreshTimerRef.current !== null) window.clearTimeout(refreshTimerRef.current);
      void client.removeChannel(channel);
    };
  }, [filter, refresh]);

  return { orders, loading, error, syncState, refresh };
}
