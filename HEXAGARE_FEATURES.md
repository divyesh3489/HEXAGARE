# HEXAGARE — Product & Business Management System

## Product & Business Feature Specification

HEXAGARE is a product, inventory, sales, billing, purchasing, finance, and business management system designed around **serial-number-based product unit tracking**.

The core inventory identity is:

Product → Variant → SKU → Product Unit → Serial Number → Barcode

A barcode is a machine-readable representation of a unique serial number. Scanning a barcode must allow the system to identify the exact physical product unit and retrieve its complete product, SKU, variant, inventory, order, and history information.

---

# 1. Core Product & Inventory Architecture

## Product Hierarchy

```text
PRODUCT
   │
   └── VARIANTS
          │
          └── SKU
                 │
                 └── PRODUCT UNITS
                        │
                        ├── Serial Number
                        ├── Barcode
                        ├── Location
                        ├── Status
                        └── History
```

Example:

```text
Hexagare Mouse Pad
│
├── 11 × 23 inch
│   │
│   └── SKU: HEX-MP-11X23-001
│       ├── HEX000001 → Barcode
│       ├── HEX000002 → Barcode
│       └── HEX000003 → Barcode
│
└── 12 × 32 inch
    │
    └── SKU: HEX-MP-12X32-001
        ├── HEX000004 → Barcode
        ├── HEX000005 → Barcode
        └── HEX000006 → Barcode
```

## Core Rules

- Product identifies the overall product.
- Variant identifies size/color/material/custom attributes.
- SKU identifies a product variant.
- Serial Number identifies an individual physical unit.
- Barcode maps to the serial number.
- Each serialized product unit must have a unique serial number.
- Each serialized product unit must have a unique barcode.
- A SKU can have many serial numbers.
- A serial number must belong to exactly one product unit.
- A barcode must map to exactly one serial number.
- Inventory quantity must be derived from product-unit status for serialized products.
- Product-unit history must be maintained throughout its lifecycle.

---

# 2. Authentication & Users

- Admin login
- User login
- Logout
- Password reset
- User roles
- Permissions
- Profile management
- Activity/audit log
- Serial number access permissions
- Barcode scanning permissions
- Inventory adjustment permissions
- Order permissions
- Billing permissions
- Purchase permissions
- Finance permissions
- Report permissions
- Settings permissions

---

# 3. Dashboard

## Sales

- Total sales
- Today's sales
- Weekly sales
- Monthly sales
- Yearly sales
- Amazon sales
- Offline sales
- Total orders
- Products sold
- Units sold

## Inventory

- Total inventory
- Total serialized units
- Available units
- Reserved units
- In-transit units
- Sold units
- Returned units
- Damaged units
- Lost units
- Low-stock products
- Out-of-stock products
- Overstock products

## Finance

- Revenue
- Taxable sales
- GST collected
- Product cost
- Amazon fees
- Courier/shipping charges
- Advertising cost
- Packaging cost
- Other expenses
- Gross profit
- Net profit
- Profit margin

## Analytics

- Sales graph
- Amazon vs Offline comparison
- Top-selling products
- Top-selling SKUs
- Low-stock products
- Recent orders
- Recent returns
- Recent barcode scans
- Recent stock movements
- Recent notifications

---

# 4. Product Management

## Product Creation

Fields:

- Product ID
- Product name
- Product description
- Product images
- Product category
- Brand
- Product status
- MRP
- Selling price
- Purchase price
- Discount
- GST percentage
- HSN/SAC
- Weight
- Dimensions
- Tags
- Notes

## Product Status

- Active
- Inactive
- Draft
- Discontinued

---

# 5. Product Pricing & GST

HEXAGARE uses **GST-inclusive selling prices**.

The user enters the final selling price that the customer pays.

Example:

```text
Selling Price = ₹1,180
GST = 18%
```

The system automatically calculates:

```text
Taxable/Base Price = ₹1,000
GST Amount = ₹180
Final Selling Price = ₹1,180
```

## Formula

```text
Base Price = Selling Price / (1 + GST% / 100)

GST Amount = Selling Price - Base Price
```

## Product Pricing Fields

```text
MRP
Selling Price (GST Inclusive)
Purchase Price
GST Rate
Taxable/Base Price (Auto)
GST Amount (Auto)
Discount
```

## Tax Support

- GST-inclusive pricing
- GST-exclusive calculation internally
- CGST
- SGST
- IGST
- GST percentage configuration
- Tax rounding configuration
- Tax calculation history

GST collected must not be treated as business profit.

---

# 6. Product Variants

Support:

- Multiple sizes
- Multiple colors
- Multiple materials
- Custom attributes
- Variant-specific SKU
- Variant-specific pricing
- Variant-specific stock
- Variant-specific barcode/serial configuration
- Variant-specific images

Example:

```text
Hexagare Mouse Pad

├── 11 × 23 inch
│   └── SKU: HEX-MP-11X23-001
│
└── 12 × 32 inch
    └── SKU: HEX-MP-12X32-001
```

---

# 7. SKU Management

SKU is created at the **variant level**, not at the individual unit level.

## Features

- Automatic SKU suggestion
- Category-based SKU
- Product-based SKU
- Variant-based SKU
- Sequential numbering
- Duplicate SKU detection
- Manual SKU editing
- SKU search
- SKU lookup
- SKU activation/deactivation

Example:

```text
SKU:
HEX-MP-11X23-001

Serial Numbers:

HEX000001
HEX000002
HEX000003
HEX000004
```

One SKU can contain many serialized units.

---

# 8. Serial Number Management

Serial number is the unique identity of an individual physical unit.

## Features

- Automatic serial number generation
- Manual serial number entry
- Sequential serial numbering
- Custom prefix
- Product-specific serial format
- Variant-specific serial format
- Starting serial number
- Bulk serial generation
- Duplicate serial detection
- Serial validation
- Serial search
- Serial lookup
- Serial import
- Serial export
- Serial status
- Serial history

## Example

```text
HEX000001
HEX000002
HEX000003
```

Custom format example:

```text
HEX-MP-11X23-000001
```

---

# 9. Product Unit Management

Each physical serialized item must have a Product Unit record.

## Product Unit Fields

```text
Unit ID
Product ID
Variant ID
SKU
Serial Number
Barcode
Location
Status
Purchase Cost
Created At
Created By
Updated At
Updated By
```

## Example

```text
Unit ID:
UNIT-000001

Product:
Hexagare Mouse Pad

Variant:
11 × 23 inch

SKU:
HEX-MP-11X23-001

Serial Number:
HEX000001

Barcode:
8901234567890

Location:
Warehouse

Status:
AVAILABLE
```

---

# 10. Bulk Unit Generation

Users must be able to generate multiple product units for a specific product/variant.

## Flow

```text
Select Product
      ↓
Select Variant
      ↓
Select SKU
      ↓
Enter Quantity
      ↓
Set Starting Serial Number
      ↓
Select Location
      ↓
Generate Units
      ↓
Generate Barcodes
      ↓
Create Product Units
      ↓
Add Units to Inventory
      ↓
Generate PDF Labels
```

## Example

```text
Product:
Hexagare Mouse Pad

Variant:
11 × 23 inch

SKU:
HEX-MP-11X23-001

Quantity:
500

Starting Serial:
HEX000001

Location:
Warehouse
```

System generates:

```text
HEX000001
HEX000002
HEX000003
...
HEX000500
```

Every generated serial number creates a Product Unit record.

## Initial Status

Generated units should normally be:

```text
Status: AVAILABLE
Location: Selected Location
```

or:

```text
Status: RECEIVED
```

depending on the inventory workflow configuration.

---

# 11. Bulk Serial Number & Barcode PDF

Users must be able to generate serial numbers and barcodes in bulk for a particular product/variant.

## Features

- Select product
- Select variant
- Select SKU
- Enter quantity
- Set starting serial number
- Set serial prefix
- Select barcode type
- Select label size
- Select PDF layout
- Generate units
- Generate serial numbers
- Generate barcodes
- Save mappings
- Add units to inventory
- Generate PDF
- Download PDF
- Print PDF
- Reprint labels
- Generation history

## Supported Barcode Types

- Code 128
- EAN-13
- UPC
- QR Code

## Label Content

```text
HEXAGARE

Hexagare Mouse Pad
11 × 23 inch

SKU:
HEX-MP-11X23-001

Serial:
HEX000001

[ BARCODE ]
```

Optional fields:

- Product name
- Variant
- SKU
- Serial number
- MRP
- Selling price
- QR code
- Custom text
- Logo

## PDF Formats

- A4
- Multiple labels per page
- Custom label dimensions
- Thermal printer format
- Custom margins
- Horizontal layout
- Vertical layout

## Transaction Safety

Bulk generation must be transactional.

Example:

```text
Requested: 500
Created: 500
PDF: Generated
```

If generation fails:

```text
Requested: 500
Created: 0
Status: Failed
```

The system must prevent partial/unknown unit creation.

---

# 12. Barcode Management

Barcode is a machine-readable representation of the serial number.

Relationship:

```text
Barcode
   ↓
Serial Number
   ↓
Product Unit
   ↓
SKU
   ↓
Variant
   ↓
Product
```

## Features

- Generate barcode automatically
- Generate barcode from serial number
- Barcode/SN mapping
- Barcode uniqueness validation
- Barcode download
- Barcode PDF
- Bulk barcode generation
- Barcode label generation
- Print barcode
- Reprint barcode
- Barcode search
- Barcode lookup

---

# 13. Barcode Scanner

Support:

- Mobile camera scanner
- Desktop barcode scanner
- USB scanner
- Product lookup
- Serial number lookup
- SKU lookup
- Inventory lookup
- Add scanned unit to invoice
- Stock adjustment
- Stock transfer
- Return processing
- Unit history lookup

## Scan Flow

```text
SCAN BARCODE
     ↓
Decode Serial Number
     ↓
Find Product Unit
     ↓
Find SKU
     ↓
Find Variant
     ↓
Find Product
     ↓
Display Unit Details
```

Example:

```text
Serial:
HEX00001245

Product:
Hexagare Mouse Pad

Variant:
11 × 23 inch

SKU:
HEX-MP-11X23-001

Price:
₹1,180

GST:
18%

Location:
Warehouse

Status:
AVAILABLE
```

---

# 14. Product Unit Status

Every serialized unit must have a lifecycle status.

## Main Statuses

```text
GENERATED
AVAILABLE
RESERVED
IN_TRANSIT
SOLD
RETURNED
DAMAGED
LOST
CANCELLED
```

## Status Meaning

### GENERATED

Serial number has been generated but the unit has not yet entered usable inventory.

### AVAILABLE

Unit is available for sale or allocation.

### RESERVED

Unit is allocated to an order/invoice but the sale has not been completed.

### IN_TRANSIT

Unit is moving between locations or is in an active shipment/transfer process.

### SOLD

Sale has been completed.

### RETURNED

Unit has been returned by a customer.

Returned units must be classified as:

```text
Resellable
Damaged
```

Resellable units can return to:

```text
AVAILABLE
```

Damaged units become:

```text
DAMAGED
```

### DAMAGED

Unit cannot currently be sold.

### LOST

Physical unit cannot be located.

### CANCELLED

Unit/order allocation has been cancelled.

---

# 15. Status Transition Rules

Status must not be changed arbitrarily.

Valid examples:

```text
GENERATED → AVAILABLE

AVAILABLE → RESERVED

RESERVED → AVAILABLE

RESERVED → SOLD

AVAILABLE → IN_TRANSIT

IN_TRANSIT → AVAILABLE

IN_TRANSIT → SOLD

SOLD → RETURNED

RETURNED → AVAILABLE

RETURNED → DAMAGED
```

Certain transitions must only happen through the appropriate business action.

Examples:

```text
SOLD → RETURNED
```

must happen through Return processing.

```text
AVAILABLE → IN_TRANSIT
```

must happen through Stock Transfer.

```text
AVAILABLE → RESERVED
```

must happen through Order/Invoice reservation.

---

# 16. Location Management

Initial locations:

```text
Amazon
Offline
Warehouse
```

Future locations:

```text
Amazon FBA
Amazon FBM
Warehouse 1
Warehouse 2
Offline Store
```

## Features

- Multiple locations
- Location-wise inventory
- Location-wise serial numbers
- Stock transfer
- Transfer history
- Location-based stock reports

## Important Rule

Location and Status are separate fields.

Example:

```text
Serial:
HEX00001245

Status:
IN_TRANSIT

Current Location:
Warehouse

Destination:
Offline Store
```

After receiving:

```text
Status:
AVAILABLE

Location:
Offline Store
```

---

# 17. Inventory Management

## Quantity Inventory

- Total stock
- Available stock
- Reserved stock
- In-transit stock
- Sold stock
- Damaged stock
- Returned stock
- Lost stock
- Opening stock
- Stock adjustment
- Stock increase
- Stock decrease
- Stock history
- Stock ledger

## Serialized Inventory

Example:

```text
SKU:
HEX-MP-11X23-001

Total Units: 100
Available: 70
Reserved: 5
In Transit: 10
Sold: 13
Damaged: 2
```

For serialized products, these quantities should be calculated from Product Unit statuses.

---

# 18. Inventory Alerts

- Low-stock alert
- Out-of-stock alert
- Overstock alert
- Minimum stock level
- Maximum stock level
- Duplicate serial alert
- Invalid barcode alert
- Missing serial number
- Unassigned unit
- Unit status conflict
- Location mismatch
- Email notification
- Dashboard notification

---

# 19. Sales Channels

## Current

- Amazon
- Offline

## Future

- Hexagare website
- Shopify
- Flipkart
- Meesho
- Other marketplaces

## Channel Features

- Channel-wise sales
- Channel-wise revenue
- Channel-wise orders
- Channel-wise profit
- Channel-wise fees
- Channel-wise shipping costs
- Channel-wise returns

---

# 20. Amazon Sales Management

## Order Management

- Amazon order import
- Amazon order ID
- Amazon SKU
- HEXAGARE SKU mapping
- Product mapping
- Variant mapping
- Serial number assignment
- Order status
- Shipment status
- Delivered orders
- Cancelled orders
- Returned orders

## Amazon Financial Data

- Customer selling price
- GST
- Taxable sales value
- Amazon fees
- Referral fees
- Closing fees
- Fulfillment fees
- Shipping/courier charges
- Other Amazon charges
- Advertising cost
- Return fees
- Refunds
- Settlement amount
- Net revenue
- Amazon profit

Amazon fees and charges must be configurable because rates can change.

---

# 21. Amazon Profit Calculation

Example:

```text
Selling Price (GST Inclusive)
              ↓
         Remove GST
              ↓
      Taxable Sales Value
              ↓
        - Amazon Fees
        - Courier Charges
        - Advertising
        - Product Cost
        - Packaging
        - Other Expenses
              ↓
          NET PROFIT
```

Example:

```text
Customer Selling Price       ₹1,180
GST                          ₹180
Taxable Sales Value          ₹1,000

Amazon Fee                   ₹150
Courier                      ₹80
Advertising                  ₹50

Product Cost                 ₹400

Net Profit                   ₹320
```

---

# 22. Amazon Fee Configuration

Admin must be able to configure:

- Fee name
- Fee type
- Percentage fee
- Fixed fee
- Applicable channel
- Applicable category
- Applicable product
- Effective from
- Effective to

The system must not hard-code Amazon fee rates.

---

# 23. Offline POS / Billing

## New Bill

- Create new bill
- Barcode scanning
- Product search
- SKU search
- Serial number lookup
- Add/remove product
- Quantity
- Discount
- GST
- Tax calculation
- Subtotal
- Total

## Payment

- Cash
- UPI
- Card
- Bank transfer
- Multiple payment methods
- Partial payment
- Credit/Due payment
- Refund

## Bill Management

- Hold bill
- Resume bill
- Cancel bill
- Draft bill
- Completed bill

---

# 24. Barcode-to-Invoice Flow

The primary offline billing workflow:

```text
SCAN BARCODE
      ↓
Find Serial Number
      ↓
Find Product Unit
      ↓
Find SKU
      ↓
Find Variant
      ↓
Find Product
      ↓
Validate Unit Status
      ↓
Add Exact Unit to Invoice
```

The user should not need to manually enter:

- Product
- SKU
- Serial number
- Price
- GST

These values should be loaded automatically.

---

# 25. Invoice Reservation

When an invoice/order is being prepared but not completed:

```text
AVAILABLE
    ↓
RESERVED
```

Reserved units cannot be sold to another customer.

If the invoice/order is cancelled:

```text
RESERVED
    ↓
AVAILABLE
```

---

# 26. Complete Sale Flow

When the user clicks:

```text
COMPLETE SALE
```

The system must atomically:

```text
Create Invoice
      ↓
Create Order
      ↓
Record Payment
      ↓
Mark Serial Number as SOLD
      ↓
Update Inventory
      ↓
Update Stock Ledger
      ↓
Update Sales
      ↓
Update Profit
      ↓
Create Audit Log
```

No manual inventory adjustment should be required after a completed sale.

---

# 27. Order Management

Every completed sale must automatically create/update an Order.

## Order Types

- Offline order
- Amazon order

## Order Status

Offline:

```text
Draft
Reserved
Completed
Cancelled
Returned
```

Amazon:

```text
Pending
Confirmed
Shipped
In Transit
Delivered
Cancelled
Returned
Refunded
```

## Order Information

- Order ID
- Invoice ID
- Customer
- Channel
- Products
- Variants
- SKU
- Serial numbers
- Quantity
- Selling price
- GST
- Discount
- Payment
- Fees
- Shipping
- Profit
- Order status
- Created date
- Updated date

---

# 28. Invoice Management

- Automatic invoice number
- Invoice generation
- Invoice PDF
- Print invoice
- Download invoice
- Email invoice
- WhatsApp invoice
- Invoice history
- Invoice search
- Invoice cancellation
- Duplicate invoice
- Invoice status

## Invoice Number Example

```text
HEX-INV-001245
```

## Invoice Pricing

The invoice must display GST breakdown.

Example:

```text
Product:
Hexagare Mouse Pad

SKU:
HEX-MP-11X23-001

Serial:
HEX00001245

Taxable Value:
₹1,000

CGST @ 9%:
₹90

SGST @ 9%:
₹90

Total:
₹1,180
```

For inter-state sales:

```text
Taxable Value:
₹1,000

IGST @ 18%:
₹180

Total:
₹1,180
```

---

# 29. Customer Management

## Customer Fields

- Customer ID
- Customer name
- Phone
- Email
- Address
- GSTIN
- Customer notes
- Customer history
- Order history
- Total purchases
- Total refunds
- Outstanding amount

## Customer → Serial Number History

Customers should be linked to purchased serialized units.

Example:

```text
Customer:
Rahul

Purchased Units:

HEX00001245
HEX00001246
HEX00001300
```

This helps with returns, replacements, and customer support.

---

# 30. Walk-in Customers

Support:

```text
Walk-in Customer
```

No registration required.

User can complete a quick offline sale without creating a permanent customer record.

---

# 31. Sales Returns

Support:

- Amazon returns
- Offline returns
- Return order
- Return quantity
- Return reason
- Refund amount
- Resellable condition
- Damaged condition
- Stock restoration
- Return history

## Serialized Return Flow

```text
Order
   ↓
Product
   ↓
Serial Number
   ↓
Return
   ↓
Condition
   ├── Resellable
   └── Damaged
```

Resellable:

```text
RETURNED → AVAILABLE
```

Damaged:

```text
RETURNED → DAMAGED
```

---

# 32. Purchase Management

## Suppliers

- Supplier name
- Company
- Phone
- Email
- Address
- GSTIN
- Payment terms
- Supplier balance
- Supplier history

## Purchases

- Purchase order
- Supplier
- Product
- Variant
- SKU
- Quantity
- Purchase price
- Tax
- Discount
- Purchase invoice
- Payment
- Pending payment
- Receive stock
- Generate/import serial numbers
- Purchase history

---

# 33. Purchase → Unit Flow

When serialized stock is received:

```text
Purchase Order
      ↓
Supplier
      ↓
Product
      ↓
Variant
      ↓
SKU
      ↓
Generate/Import Serial Numbers
      ↓
Create Product Units
      ↓
Assign Location
      ↓
Mark Units Available
```

Example:

```text
Purchase Quantity: 100

SKU:
HEX-MP-11X23-001

Serial Numbers:
HEX000001 → HEX000100
```

---

# 34. Payments

Supported payment methods:

- Cash
- UPI
- Card
- Bank transfer
- Credit
- Partial payment
- Refund

Features:

- Payment history
- Payment allocation
- Due amount
- Refund tracking
- Payment status

---

# 35. Expenses

Categories:

- Amazon fees
- Shipping
- Courier
- Packaging
- Advertising
- Manufacturing
- Raw materials
- Offline expenses
- Other expenses

Features:

- Expense categories
- Expense creation
- Expense editing
- Expense reports
- Expense history
- Date-wise expenses
- Channel-wise expenses

---

# 36. Profit Calculation

## General Profit

```text
Sales Revenue
      ↓
- Product Cost
- Packaging
- Shipping
- Amazon Fees
- Advertising
- Other Expenses
      ↓
NET PROFIT
```

GST collected should be separately reported and should not be treated as profit.

## Reports should show

- Gross sales including GST
- Taxable sales
- GST collected
- Discounts
- Refunds
- Product cost
- Amazon fees
- Shipping
- Advertising
- Packaging
- Other expenses
- Gross profit
- Net profit
- Profit margin

---

# 37. Serial Number Profit Tracking

For serialized units, profit can optionally be tracked at unit level.

Example:

```text
Serial:
HEX00001245

Purchase Cost:
₹400

Taxable Selling Value:
₹1,000

Amazon Fees:
₹150

Courier:
₹80

Advertising:
₹50

Unit Profit:
₹320
```

---

# 38. Sales Reports

Support:

- Daily
- Weekly
- Monthly
- Yearly
- Custom date range
- Amazon
- Offline
- Product-wise
- Variant-wise
- SKU-wise
- Category-wise
- Serial-number-wise

Metrics:

- Orders
- Units sold
- Gross sales
- Taxable sales
- GST
- Discounts
- Refunds
- Revenue
- Profit

---

# 39. Inventory Reports

- Current stock
- Stock valuation
- Stock movement
- Low stock
- Out of stock
- Overstock
- Dead stock
- Damaged stock
- Returned stock
- Reserved stock
- In-transit stock
- Location-wise stock
- SKU-wise stock

---

# 40. Serial Number Reports

Dedicated serialized inventory reports:

- Total serial numbers
- Available serial numbers
- Reserved serial numbers
- In-transit serial numbers
- Sold serial numbers
- Returned serial numbers
- Damaged serial numbers
- Lost serial numbers
- Cancelled serial numbers
- Product-wise serial numbers
- SKU-wise serial numbers
- Location-wise serial numbers
- Date-wise serial numbers

---

# 41. Serial Number History

Every serial number must maintain a complete lifecycle history.

Example:

```text
HEX00001245

10 Sep 2026
Generated

10 Sep 2026
Received
Location: Warehouse

10 Sep 2026
Transferred
Warehouse → Offline

10 Sep 2026
Reserved
Invoice: HEX-INV-001245

10 Sep 2026
Sold
Order: HEX-ORD-001245

15 Sep 2026
Returned
Reason: Damaged

16 Sep 2026
Marked Damaged
```

Every history event should record:

- Event
- Previous status
- New status
- Previous location
- New location
- User
- Date/time
- Reason
- Related order
- Related invoice
- Related purchase
- Related transfer

---

# 42. Product Reports

- Best-selling products
- Worst-selling products
- Slow-moving products
- Revenue by product
- Profit by product
- Units sold
- Units available
- Units reserved
- Units in transit
- Units damaged

---

# 43. Financial Reports

- Revenue
- Gross sales
- Taxable sales
- GST collected
- Product cost
- Expenses
- Amazon fees
- Courier charges
- Advertising cost
- Gross profit
- Net profit
- Profit margin
- Refunds
- Outstanding payments

---

# 44. Export

Support:

- Excel
- CSV
- PDF
- Print

Exports should support:

- Sales
- Orders
- Products
- SKUs
- Product Units
- Serial Numbers
- Inventory
- Purchases
- Customers
- Suppliers
- Expenses
- Payments
- Profit
- GST
- Returns

---

# 45. Label Management

## Product Labels

Support:

- Product name
- Variant
- SKU
- Serial number
- Barcode
- QR code
- Price
- Custom text
- Custom label size
- Bulk labels
- A4 printing
- Thermal printer support

## Label Example

```text
┌─────────────────────────────┐
│           HEXAGARE          │
│                             │
│   Hexagare Mouse Pad        │
│   11 × 23 inch              │
│                             │
│   SKU: HEX-MP-11X23-001     │
│                             │
│   [ BARCODE ]               │
│                             │
│   HEX00001245               │
└─────────────────────────────┘
```

---

# 46. Product Image Management

- Upload product image
- Multiple images
- Main image
- Image gallery
- Image compression
- Thumbnail generation
- Replace image
- Delete image

Future:

- Background removal
- Image optimization
- Marketplace image templates

---

# 47. Notifications

## Dashboard Notifications

- Low stock
- Out of stock
- New order
- Return
- Payment pending
- Supplier payment due
- Invoice generated
- In-transit stock
- Serial number conflict
- Barcode conflict
- System notifications

## Channels

- Dashboard
- Email
- WhatsApp

---

# 48. Mobile / PWA

- Mobile-friendly dashboard
- Mobile product management
- Mobile inventory
- Mobile billing
- Mobile barcode scanner
- Mobile stock adjustment
- Mobile stock transfer
- Mobile serial number lookup
- Mobile product-unit history
- Installable PWA

## Mobile Scan Experience

```text
        📷

    SCAN BARCODE
```

After scanning:

```text
Serial:
HEX00001245

Product:
Hexagare Mouse Pad

Variant:
11 × 23 inch

SKU:
HEX-MP-11X23-001

Location:
Warehouse

Status:
AVAILABLE

[SELL]
[RESERVE]
[TRANSFER]
[ADJUST]
[RETURN]
[HISTORY]
```

---

# 49. Business Settings

- Hexagare logo
- Business name
- Address
- Phone
- Email
- GSTIN
- Invoice settings
- Tax settings
- Currency
- Invoice numbering
- Serial number settings
- Barcode settings
- Label settings
- Notification settings

---

# 50. Serial Number Settings

Admin configuration:

- Enable/disable serialization by product
- Serial number prefix
- Serial number format
- Starting number
- Sequential numbering
- Product-specific prefix
- Variant-specific prefix
- Manual serial entry
- Automatic serial generation
- Duplicate validation
- Required serial number
- Serial number length

Example:

```text
Prefix:
HEX-MP

Starting Number:
000001

Generated:
HEX-MP-000001
HEX-MP-000002
HEX-MP-000003
```

---

# 51. Barcode Settings

- Barcode type
- Code 128
- EAN-13
- UPC
- QR Code
- Barcode generation rules
- Barcode label size
- PDF layout
- Printer settings
- Thermal printer configuration
- Reprint settings

---

# 52. System Settings

- Users
- Roles
- Permissions
- Categories
- Units
- Tax rates
- Payment methods
- Sales channels
- Locations
- Order statuses
- Product statuses
- Serial number statuses
- Expense categories
- Amazon fee configuration

---

# 53. Security & Audit

## Role-Based Security

- Role-based permissions
- Module permissions
- Action-level permissions
- Delete restrictions
- Soft delete

## Login Security

- Login history
- Failed login tracking
- Session management
- Logout tracking

## Activity Log

Track:

- Product creation
- Product modification
- Variant modification
- SKU modification
- Serial number creation
- Serial number modification
- Barcode generation
- Barcode changes
- Unit creation
- Stock changes
- Location changes
- Status changes
- Price changes
- Invoice creation
- Invoice modification
- Invoice cancellation
- Order creation
- Order cancellation
- Returns
- Purchase creation
- Payment changes
- Expense changes
- User changes
- Settings changes

---

# 54. Backup

- Database backup
- Backup history
- Manual backup
- Automatic backup
- Restore capability
- Backup status
- Backup audit log

---

# 55. Critical Business Rules

These rules must be enforced throughout the application.

## Rule 1 — Serial Number Identity

```text
Barcode → Serial Number → Product Unit
```

A barcode must never directly represent only a generic product/SKU.

---

## Rule 2 — SKU Identity

```text
Product → Variant → SKU
```

A SKU represents a variant, not an individual serialized unit.

---

## Rule 3 — Unique Unit

Every physical serialized product must have:

```text
Unique Unit ID
Unique Serial Number
Unique Barcode
```

---

## Rule 4 — Barcode Scan

Scanning a barcode must retrieve:

```text
Serial Number
Product Unit
Product
Variant
SKU
Price
GST
Location
Status
History
```

---

## Rule 5 — Prevent Double Sale

A unit with status:

```text
SOLD
DAMAGED
LOST
```

must not be allowed to be added to a new sale.

---

## Rule 6 — Reservation

Reserved units cannot be sold to another order/customer.

```text
AVAILABLE → RESERVED
```

If the reservation is cancelled:

```text
RESERVED → AVAILABLE
```

---

## Rule 7 — Sale

When a sale is completed:

```text
Invoice Created
Order Created
Payment Recorded
Serial → SOLD
Inventory Updated
Stock Ledger Updated
Profit Updated
Audit Log Created
```

These operations should be atomic.

---

## Rule 8 — Inventory

Serialized inventory quantity should be calculated from Product Unit statuses.

Example:

```text
100 Total Units

70 AVAILABLE
5 RESERVED
10 IN_TRANSIT
13 SOLD
2 DAMAGED
```

---

## Rule 9 — Location

Location and status are separate concepts.

Example:

```text
Status:
IN_TRANSIT

Current Location:
Warehouse

Destination:
Offline Store
```

---

## Rule 10 — Returns

Returns must identify the exact serial number.

```text
Order
 ↓
SKU
 ↓
Serial Number
 ↓
Return
```

---

## Rule 11 — GST

Selling price entered by the user is GST-inclusive.

The system automatically calculates:

```text
Taxable Price
GST Amount
Final Selling Price
```

GST must not be counted as profit.

---

## Rule 12 — Amazon Profit

Amazon profit must account for:

```text
Taxable Sales
- Product Cost
- Amazon Fees
- Courier Charges
- Advertising
- Packaging
- Other Expenses
```

---

## Rule 13 — Bulk Generation

Bulk serial/barcode generation must:

```text
Generate Serial Numbers
       ↓
Create Product Units
       ↓
Generate Barcodes
       ↓
Map Barcode → Serial Number
       ↓
Add Units to Inventory
       ↓
Generate PDF
```

The PDF generation must not create units independently from inventory.

---

# 56. Recommended Main Navigation

```text
Dashboard

Products
├── Products
├── Variants
├── SKUs
├── Product Units
├── Serial Numbers
└── Bulk Generate Units

Inventory
├── Overview
├── Stock
├── Locations
├── Transfers
├── Adjustments
├── Stock Ledger
└── Alerts

Sales
├── New Bill
├── Orders
├── Offline Sales
├── Amazon Sales
├── Returns
└── Invoices

Barcode
├── Scan
├── Generate Barcode
├── Bulk Generate
├── Labels
└── Print/Reprint

Purchases
├── Suppliers
├── Purchase Orders
├── Receive Stock
└── Purchase History

Customers
├── Customers
├── Walk-in Customers
└── Customer History

Finance
├── Payments
├── Expenses
├── Amazon Charges
└── Profit

Reports
├── Sales
├── Inventory
├── Serial Numbers
├── Products
├── Financial
└── Exports

Notifications

Settings
├── Business
├── Users
├── Roles & Permissions
├── Categories
├── Tax
├── Payment Methods
├── Sales Channels
├── Locations
├── Serial Numbers
├── Barcode
└── System
```

---

# 57. End-to-End Offline Sale Example

```text
1. Customer comes to store
        ↓
2. Cashier opens New Bill
        ↓
3. Cashier scans barcode
        ↓
4. Barcode → Serial Number
        ↓
5. Serial Number → Product Unit
        ↓
6. Product Unit → SKU/Variant/Product
        ↓
7. Unit validated as AVAILABLE
        ↓
8. Product added to invoice
        ↓
9. GST automatically calculated
        ↓
10. Customer pays
        ↓
11. Invoice completed
        ↓
12. Order created
        ↓
13. Payment recorded
        ↓
14. Serial Number → SOLD
        ↓
15. Available inventory decreases
        ↓
16. Stock ledger updated
        ↓
17. Profit updated
        ↓
18. Audit log created
```

---

# 58. End-to-End Stock Transfer Example

```text
Warehouse
    ↓
Create Transfer
    ↓
Scan Product Barcode
    ↓
Serial Number Identified
    ↓
Validate AVAILABLE
    ↓
Status → IN_TRANSIT
    ↓
Destination → Offline
    ↓
Offline receives product
    ↓
Status → AVAILABLE
    ↓
Location → Offline
    ↓
Transfer History Recorded
```

---

# 59. End-to-End Return Example

```text
Customer
    ↓
Return Product
    ↓
Scan Barcode
    ↓
Find Serial Number
    ↓
Find Original Order
    ↓
Validate SOLD
    ↓
Create Return
    ↓
Refund
    ↓
Status → RETURNED
    ↓
Inspect Product
    ↓
     ┌───────────────┐
     ↓               ↓
Resellable        Damaged
     ↓               ↓
AVAILABLE        DAMAGED
```

---

# 60. End-to-End Bulk Unit Creation Example

```text
Product:
Hexagare Mouse Pad

Variant:
11 × 23 inch

SKU:
HEX-MP-11X23-001

Quantity:
500

Starting Serial:
HEX000001

Location:
Warehouse
        ↓
Generate 500 Serial Numbers
        ↓
Create 500 Product Units
        ↓
Generate 500 Barcodes
        ↓
Save Barcode/SN Mapping
        ↓
Add 500 Units to Inventory
        ↓
Generate Label PDF
        ↓
Download / Print
```

---

# 61. Future Extensibility

The architecture should allow future integration with:

- Hexagare website
- Shopify
- Flipkart
- Meesho
- Other marketplaces
- Amazon FBA
- Amazon FBM
- Multiple warehouses
- Multiple offline stores
- Warranty management
- Product replacement
- Serial-number-based customer support
- Marketplace APIs
- Advanced accounting
- GST reporting
- WhatsApp integration
- Email automation
- Advanced analytics
- AI-powered inventory forecasting

---

# 62. Primary System Principle

HEXAGARE must treat the **Product Unit / Serial Number** as the identity of the physical inventory item.

The complete relationship is:

```text
PRODUCT
   ↓
VARIANT
   ↓
SKU
   ↓
PRODUCT UNIT
   ↓
SERIAL NUMBER
   ↓
BARCODE
```

And after sale:

```text
BARCODE SCAN
      ↓
SERIAL NUMBER
      ↓
PRODUCT UNIT
      ↓
INVOICE
      ↓
ORDER
      ↓
PAYMENT
      ↓
SERIAL → SOLD
      ↓
INVENTORY UPDATE
      ↓
STOCK LEDGER
      ↓
PROFIT
      ↓
AUDIT HISTORY
```

This relationship must remain consistent across **Products, Inventory, Barcode, Billing, Orders, Amazon, Purchases, Returns, Customers, Finance, Reports, and Audit Logs**.