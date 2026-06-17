package io.mcprpc.automesh.fixtures;

import io.mcprpc.automesh.annotations.Expose;
import io.mcprpc.automesh.annotations.Ignore;
import io.mcprpc.automesh.annotations.InputMode;
import java.util.Map;

public final class BillingService {
    @Expose(
        name = "billing.calculateVat",
        description = "Calculate VAT",
        tags = {"billing"},
        roles = {"billing", "admin"},
        inputMode = InputMode.POSITIONAL,
        parameters = {"amount", "rate"},
        costCpuWeight = 1
    )
    public VatResult calculateVat(double amount, double rate) {
        return new VatResult(amount * rate);
    }

    public Map<String, Object> createInvoice(String customerId) {
        return Map.of("invoiceId", "INV-001", "customerId", customerId);
    }

    @Ignore
    public String dangerousFunction() {
        return "ignored";
    }

    public String _privateStyleMethod() {
        return "ignored";
    }

    public record VatResult(double vat) {
    }
}
