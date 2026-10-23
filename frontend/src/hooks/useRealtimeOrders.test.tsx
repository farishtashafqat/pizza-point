// @vitest-environment jsdom
import { act, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { CustomerOrder } from '../types';

const realtime = vi.hoisted(() => {
  const state: { eventHandler?: () => void } = {};
  const channel = {
    on: vi.fn((_event: string, _config: unknown, callback: () => void) => { state.eventHandler = callback; return channel; }),
    subscribe: vi.fn((callback: (status: string) => void) => { callback('SUBSCRIBED'); return channel; }),
  };
  return { state, channel, client: { channel: vi.fn(() => channel), removeChannel: vi.fn(async () => undefined) } };
});
vi.mock('../services/supabase', () => ({ supabase: realtime.client }));

import { useRealtimeOrders } from './useRealtimeOrders';

const order = (status: CustomerOrder['status']): CustomerOrder => ({
  id: 'order-1', order_number: 7, order_type: 'pickup', customer_name: 'Customer', phone: '03001234567', delivery_address: null,
  notes: null, payment_method: 'pay_at_restaurant', status, total: 500, created_at: '2026-10-14T12:00:00Z', order_items: [],
});

describe('useRealtimeOrders', () => {
  it('uses a scoped event only to refetch authoritative data and reports one status change', async () => {
    let current = [order('Confirmed')];
    const loadOrders = vi.fn(async () => current);
    const changed = vi.fn();
    function Harness() { const state = useRealtimeOrders({ loadOrders, filter: 'customer_id=eq.customer-1', onChange: changed }); return <><span>{state.syncState}</span><span>{state.orders[0]?.status ?? 'empty'}</span></>; }
    render(<Harness />);
    await screen.findByText('live');
    await screen.findByText('Confirmed');
    expect(realtime.client.channel).toHaveBeenCalledWith('orders-sync:customer_id=eq.customer-1');
    expect(realtime.channel.on).toHaveBeenCalledWith('postgres_changes', expect.objectContaining({ filter: 'customer_id=eq.customer-1', table: 'orders' }), expect.any(Function));
    current = [order('Preparing')];
    await act(async () => { realtime.state.eventHandler?.(); });
    await waitFor(() => expect(screen.getByText('Preparing')).toBeTruthy());
    expect(changed).toHaveBeenCalledTimes(1);
    expect(changed).toHaveBeenCalledWith(expect.objectContaining({ kind: 'status', previousStatus: 'Confirmed' }));
  });
});
