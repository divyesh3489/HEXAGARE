/** Shapes returned by `/api/v1/expenses/` (Phase 13). */

export const EXPENSE_CATEGORIES = [
  "AMAZON_FEES",
  "SHIPPING",
  "COURIER",
  "PACKAGING",
  "ADVERTISING",
  "MANUFACTURING",
  "RAW_MATERIALS",
  "OFFLINE_EXPENSES",
  "OTHER",
] as const;

export type ExpenseCategory = (typeof EXPENSE_CATEGORIES)[number];

export const EXPENSE_CATEGORY_LABELS: Record<ExpenseCategory, string> = {
  AMAZON_FEES: "Amazon fees",
  SHIPPING: "Shipping",
  COURIER: "Courier",
  PACKAGING: "Packaging",
  ADVERTISING: "Advertising",
  MANUFACTURING: "Manufacturing",
  RAW_MATERIALS: "Raw materials",
  OFFLINE_EXPENSES: "Offline expenses",
  OTHER: "Other expenses",
};

export interface Expense {
  id: number;
  category: ExpenseCategory;
  category_display: string;
  sales_channel: number | null;
  sales_channel_code: string | null;
  amount: string;
  expense_date: string;
  note: string;
  created_by_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExpenseWriteBody {
  category: ExpenseCategory;
  sales_channel?: number | null;
  amount: string;
  expense_date: string;
  note?: string;
}
