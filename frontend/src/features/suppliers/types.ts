/** Shapes returned by `/api/v1/suppliers/` (Phase 12). */

export interface SupplierListItem {
  id: number;
  name: string;
  company: string;
  phone: string;
  email: string;
  created_at: string;
}

export interface SupplierOrder {
  id: number;
  status: string;
  reference: string;
  grand_total: string;
  balance_due: string;
  created_at: string;
}

export interface Supplier extends SupplierListItem {
  address: string;
  gstin: string;
  payment_terms: string;
  notes: string;
  updated_at: string;
  total_purchase_value: string;
  total_paid: string;
  outstanding_amount: string;
  orders: SupplierOrder[];
}

export interface SupplierWriteBody {
  name: string;
  company?: string;
  phone?: string;
  email?: string;
  address?: string;
  gstin?: string;
  payment_terms?: string;
  notes?: string;
}
