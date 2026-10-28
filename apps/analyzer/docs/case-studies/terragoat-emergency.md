# TerraGoat ec2.tf — EMERGENCY (secrets)
**File:** terraform/aws/ec2.tf (~10 KB) | **Level:** D3 | **Cost:** ~$0.007
## Found
EMERGENCY_INTERRUPT at Stage 0:
- pii_detected: true
- compliance_flags: ['GDPR', '152-ÔÇ', 'SECRETS']
- Pipeline stopped before analysis.

This is correct behavior — Terraform files often contain
hardcoded AWS keys / secrets. Rotation required.
