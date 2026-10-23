export type MenuCategory = { id:string; name:string; slug:string; sort_order:number; is_active:boolean };
export type MenuVariant = { id:string; item_id:string; name:string; price:number; sort_order:number; is_active:boolean };
export type MenuItem = { id:string; category_id:string; name:string; description:string|null; image_url:string|null; base_price:number|null; pamphlet_section:string; is_available:boolean; is_active:boolean; category?:MenuCategory; variants?:MenuVariant[]; price:number; selectedVariant?:string; selectedVariantId?:string };
export type CartLine = MenuItem & { quantity:number; selectedVariantId?:string };
export type OrderItem = {id:string;item_name:string;variant_name:string|null;quantity:number;unit_price:number;line_total:number};
export type CustomerOrder = {id:string;order_number:number;order_type:'delivery'|'pickup';customer_name:string;phone:string;delivery_address:string|null;notes:string|null;payment_method:'cash_on_delivery'|'pay_at_restaurant';status:'Pending'|'Confirmed'|'Preparing'|'Ready'|'Completed'|'Rejected'|'Cancelled';total:number;created_at:string;order_items:OrderItem[]};
