package io.mcprpc.automesh.examples;

import io.mcprpc.automesh.annotations.Expose;
import io.mcprpc.automesh.annotations.Ignore;
import io.mcprpc.automesh.annotations.InputMode;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.logging.Logger;

public final class BillingApi {
    private static final Logger LOGGER = Logger.getLogger(BillingApi.class.getName());

    @Expose(
        name = "billing.createInvoice",
        description = "Create an invoice for a customer",
        tags = {"billing", "invoice"},
        roles = {"billing", "admin"}
    )
    public Invoice createInvoice(String customerId, double amount, String currency) {
        LOGGER.info(() -> "tool_call name=billing.createInvoice customerId=" + customerId + " amount=" + amount + " currency=" + currency);
        Invoice invoice = new Invoice(
            "INV-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase(),
            customerId,
            amount,
            currency,
            "draft",
            Instant.now().toString()
        );
        LOGGER.info(() -> "tool_result name=billing.createInvoice invoiceId=" + invoice.invoiceId() + " status=" + invoice.status());
        return invoice;
    }

    @Expose(
        name = "billing.calculateVat",
        description = "Calculate VAT for an amount and rate",
        tags = {"billing", "tax"},
        inputMode = InputMode.POSITIONAL,
        parameters = {"amount", "rate"},
        costCpuWeight = 1
    )
    public TaxBreakdown calculateVat(double amount, double rate) {
        LOGGER.info(() -> "tool_call name=billing.calculateVat amount=" + amount + " rate=" + rate);
        double vat = amount * rate;
        TaxBreakdown result = new TaxBreakdown(amount, rate, vat, amount + vat);
        LOGGER.info(() -> "tool_result name=billing.calculateVat vatAmount=" + result.vatAmount() + " grossAmount=" + result.grossAmount());
        return result;
    }

    @Expose(
        name = "billing.listCurrencies",
        description = "List supported billing currencies",
        tags = {"billing", "catalog"}
    )
    public Map<String, Object> listCurrencies() {
        LOGGER.info("tool_call name=billing.listCurrencies");
        Map<String, Object> result = Map.of(
            "defaultCurrency", "EUR",
            "supported", List.of("EUR", "USD", "GBP")
        );
        LOGGER.info(() -> "tool_result name=billing.listCurrencies supported=" + result.get("supported"));
        return result;
    }

    @Ignore
    public String internalSecret() {
        return "should-not-be-published";
    }

    public record Invoice(
        String invoiceId,
        String customerId,
        double amount,
        String currency,
        String status,
        String createdAt
    ) {
    }

    public record TaxBreakdown(
        double netAmount,
        double rate,
        double vatAmount,
        double grossAmount
    ) {
    }
}
