# 07 — Evaluator Questions and Short Answers

**Q1. What problem does QuickBite solve?**  
It demonstrates how a food-delivery backend can accept orders quickly and process later steps asynchronously.

**Q2. Why use RabbitMQ?**  
RabbitMQ buffers events between services, decouples producers from consumers, and helps workers process tasks independently.

**Q3. Why does the API return `PENDING`?**  
The order is accepted first; payment, restaurant confirmation, delivery assignment, and notifications happen afterward.

**Q4. What does each worker do?**  
Payment handles payment outcome; restaurant confirms paid orders; delivery assigns a driver; notification logs or stores customer updates.

**Q5. What is a dead-letter queue?**  
It stores messages that the configured messaging policy routes there after they cannot be processed normally.

**Q6. What is idempotency?**  
It ensures that processing the same event more than once does not repeat the same business side effect.

**Q7. How can the system scale?**  
Run multiple instances of a worker consuming from the same queue and observe the distribution in logs.

**Q8. What does `/health` check?**  
It reports application health, including database and RabbitMQ connectivity.

**Q9. How was the project tested?**  
The observed test run completed with 25 passing pytest tests; API endpoints and worker logs were also exercised.

**Q10. What would you improve next?**  
Add clearer monitoring/metrics, document failure injection, record retry/DLQ tests, and automate integration tests for the complete workflow.
