import { expose, ignore } from "../../src/index.js";
import { z } from "zod";

// Object parameter style function
export function createInvoice(args: { customerId: string }) {
  return {
    invoiceId: "INV-001",
    customerId: args.customerId,
  };
}

// Wrapped positional function
export const calculateVat = expose(
  {
    name: "billing.calculateVat",
    description: "Calculate VAT",
    inputSchema: z.object({
      amount: z.number(),
      rate: z.number().optional(),
    }),
    inputMode: "positional",
    parameters: ["amount", "rate"],
    acl: { roles: ["billing", "admin"] },
    cost: { cpuWeight: 1 },
    tags: ["billing"],
  },
  (amount: number, rate: number = 0.22) => {
    return {
      vat: amount * rate,
    };
  }
);

// Ignored function
export const _privateFunction = () => {
  return "Should not be published";
};

export const dangerousFunction = ignore(() => {
  return "Should not be published either";
});
