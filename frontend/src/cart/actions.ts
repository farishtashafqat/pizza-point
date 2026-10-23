import type { CartLine, MenuItem, MenuVariant } from '../types';

export const MAX_CART_QUANTITY=99;

export type CartAction=
  | {action_id:string;type:'ADD_ITEM';item_id:string;variant_id?:string|null;quantity:number}
  | {action_id:string;type:'REMOVE_ITEM';item_id:string;variant_id?:string|null;quantity?:number}
  | {action_id:string;type:'SET_QUANTITY';item_id:string;variant_id?:string|null;quantity:number}
  | {action_id?:string;type:'GET_CART'};

export type CartActionResult={ok:boolean;duplicate?:boolean;message:string;cart:CartLine[]};
type Input={cart:CartLine[];menuItems:MenuItem[];action:unknown;appliedActionIds:Set<string>};

const copy=(cart:CartLine[])=>cart.map(line=>({...line}));
const same=(line:CartLine,itemId:string,variantId:string|null|undefined)=>line.id===itemId&&(line.selectedVariantId||null)===(variantId||null);
const validId=(value:unknown)=>typeof value==='string'&&value.trim().length>0&&value.length<=120;
const idOrNull=(value:unknown):string|null=>validId(value)?value as string:null;
const validQuantity=(value:unknown,min:number)=>Number.isInteger(value)&&Number(value)>=min&&Number(value)<=MAX_CART_QUANTITY;
const rejected=(cart:CartLine[],message:string):CartActionResult=>({ok:false,message,cart:copy(cart)});

function parse(value:unknown):CartAction|null{
  if(!value||typeof value!=='object'||Array.isArray(value))return null;
  const raw=value as Record<string,unknown>;
  const actionId=idOrNull(raw.action_id),itemId=idOrNull(raw.item_id);
  if(raw.type==='GET_CART')return {type:'GET_CART',...(actionId?{action_id:actionId}: {})};
  if(!actionId||!itemId||typeof raw.type!=='string')return null;
  const variantId=raw.variant_id===undefined||raw.variant_id===null?null:idOrNull(raw.variant_id);
  if(raw.variant_id!==undefined&&raw.variant_id!==null&&!variantId)return null;
  if(raw.type==='ADD_ITEM'&&validQuantity(raw.quantity,1))return {action_id:actionId,type:'ADD_ITEM',item_id:itemId,variant_id:variantId,quantity:raw.quantity as number};
  if(raw.type==='REMOVE_ITEM'&&(raw.quantity===undefined||validQuantity(raw.quantity,1)))return {action_id:actionId,type:'REMOVE_ITEM',item_id:itemId,variant_id:variantId,...(raw.quantity===undefined?{}:{quantity:raw.quantity as number})};
  if(raw.type==='SET_QUANTITY'&&validQuantity(raw.quantity,0))return {action_id:actionId,type:'SET_QUANTITY',item_id:itemId,variant_id:variantId,quantity:raw.quantity as number};
  return null;
}

function availableItem(menu:MenuItem[],itemId:string,variantId:string|null|undefined):{item:MenuItem;variant:MenuVariant|undefined}|null{
  const item=menu.find(candidate=>candidate.id===itemId);
  if(!item||!item.is_active||!item.is_available)return null;
  const variants=(item.variants||[]).filter(variant=>variant.is_active);
  const variant=variantId?variants.find(candidate=>candidate.id===variantId):undefined;
  if(variantId&&!variant)return null;
  if((variants.length>0&&!variant)||(!variants.length&&item.base_price===null))return null;
  return {item,variant};
}

/** Applies only validated structured actions; it never parses AI/chat text. */
export function applyCartAction({cart,menuItems,action,appliedActionIds}:Input):CartActionResult{
  const parsed=parse(action);
  if(!parsed)return rejected(cart,'Invalid structured cart action.');
  if(parsed.type==='GET_CART')return {ok:true,message:'Current cart returned.',cart:copy(cart)};
  if(appliedActionIds.has(parsed.action_id))return {ok:true,duplicate:true,message:'This action was already applied.',cart:copy(cart)};
  const existing=cart.find(line=>same(line,parsed.item_id,parsed.variant_id));
  if(parsed.type==='REMOVE_ITEM'){
    if(!existing)return rejected(cart,'That item is not in the cart.');
    const next=parsed.quantity&&parsed.quantity<existing.quantity?cart.map(line=>same(line,parsed.item_id,parsed.variant_id)?{...line,quantity:line.quantity-parsed.quantity!}:line):cart.filter(line=>!same(line,parsed.item_id,parsed.variant_id));
    appliedActionIds.add(parsed.action_id);return {ok:true,message:'Cart updated.',cart:next};
  }
  if(parsed.type==='SET_QUANTITY'&&parsed.quantity===0){
    if(!existing)return rejected(cart,'That item is not in the cart.');
    appliedActionIds.add(parsed.action_id);return {ok:true,message:'Cart updated.',cart:cart.filter(line=>!same(line,parsed.item_id,parsed.variant_id))};
  }
  if(parsed.type==='SET_QUANTITY'&&existing&&parsed.quantity<=existing.quantity){
    const next=cart.map(line=>same(line,parsed.item_id,parsed.variant_id)?{...line,quantity:parsed.quantity}:line);
    appliedActionIds.add(parsed.action_id);return {ok:true,message:'Cart updated.',cart:next};
  }
  const resolved=availableItem(menuItems,parsed.item_id,parsed.variant_id);
  if(!resolved)return rejected(cart,'The requested item, variant, or availability is no longer valid.');
  const quantity=parsed.type==='ADD_ITEM'?(existing?.quantity||0)+parsed.quantity:parsed.quantity;
  if(quantity>MAX_CART_QUANTITY)return rejected(cart,`A cart line cannot exceed ${MAX_CART_QUANTITY} items.`);
  const price=resolved.variant?.price??resolved.item.base_price;
  if(price===null||price===undefined)return rejected(cart,'The requested item does not have a valid price.');
  const line:CartLine={...resolved.item,price,selectedVariant:resolved.variant?.name,selectedVariantId:resolved.variant?.id,quantity};
  const next=existing?cart.map(candidate=>same(candidate,parsed.item_id,parsed.variant_id)?line:candidate):[...cart,line];
  appliedActionIds.add(parsed.action_id);return {ok:true,message:'Cart updated.',cart:next};
}

/** A batch is all-or-nothing, including its retry identifiers. */
export function applyCartActions({cart,menuItems,actions,appliedActionIds}:{cart:CartLine[];menuItems:MenuItem[];actions:unknown[];appliedActionIds:Set<string>}):CartActionResult{
  if(!Array.isArray(actions)||!actions.length)return rejected(cart,'No structured cart actions were supplied.');
  const parsedActions=actions.map(parse);if(parsedActions.some(action=>!action))return rejected(cart,'No cart changes were made: Invalid structured cart action.');
  const validActions=parsedActions as CartAction[];
  const batchIds=new Set<string>();for(const action of validActions){if(action.type!=='GET_CART'&&batchIds.has(action.action_id))return rejected(cart,'No cart changes were made: Duplicate action IDs were supplied.');if(action.type!=='GET_CART')batchIds.add(action.action_id);}
  const pendingIds=new Set(appliedActionIds),originalIds=new Set(appliedActionIds);let next=copy(cart);
  for(const action of validActions){const result=applyCartAction({cart:next,menuItems,action,appliedActionIds:pendingIds});if(!result.ok)return rejected(cart,`No cart changes were made: ${result.message}`);next=result.cart;}
  for(const id of pendingIds)if(!originalIds.has(id))appliedActionIds.add(id);
  return {ok:true,message:'Cart updated.',cart:next};
}
