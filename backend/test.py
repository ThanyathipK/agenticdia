# backend/test_agents.py
import asyncio
import json
from app.agents import prd_workflow

async def main():
    print("🚀 เริ่มต้นทดสอบระบบ Multi-Agent Workflow...")
    
    # 1. จำลองข้อมูล Input แบบดิบๆ ที่มาจาก Product Owner (สไตล์บ้านๆ หยาบๆ)
    # mock_state = {
    #     "project_id": "PROJ-BANK-999",
    #     "raw_input": (
    #         "อยากได้ระบบโอนเงินผ่าน PromptPay QR Code สำหรับร้านค้า "
    #         "โดยร้านค้าต้องเห็นเงินเข้าแบบ Real-time และระบบต้องปลอดภัยมากๆ "
    #         "ถ้าเกิดเน็ตหลุดระหว่างโอนเงิน ระบบต้องไม่ตัดเงินเบิ้ลนะ"
    #     ),
    #     "current_version": 1,
    #     "version_history_summaries": "No previous history."
    # }

    # ลองเปลี่ยน raw_input ใน test.py เป็นแบบนี้เพื่อทดสอบให้ผ่าน Audit:
    mock_state = {
        "project_id": "PROJ-BANK-999",
        "raw_input": (
            "อยากได้ระบบโอนเงินผ่าน PromptPay QR Code สำหรับร้านค้า "
            "1. ระบบต้องรองรับ Idempotency Key โดยใช้ Transaction ID ร่วมกับ Merchant ID เพื่อป้องกันการจ่ายเงินซ้ำใน 24 ชั่วโมง "
            "2. มีระบบเก็บ Audit Logging ลงฐานข้อมูลที่เข้ารหัส AES-256 ทุกๆ ขั้นตอน "
            "3. ข้อมูล PII เช่น เลขบัญชีและบัตรประชาชนต้องทำ Data Masking ใน Log เสมอ "
            "4. มีระบบ Timeout ที่ 5 วินาที และใช้ Circuit Breaker ในการ Retry ไปยังธนาคารแห่งประเทศไทยสูงสุด 3 ครั้ง "
            "5. หากเน็ตหลุดระหว่างทาง ระบบจะใช้กระบวนการสองเฟส (Two-Phase Commit) เพื่อทำ Database Rollback เสมอ"
        ),
        "current_version": 1,
        "version_history_summaries": "No previous history."
    }

    try:
        # 2. ส่งข้อมูลเข้าเครือข่าย LangGraph (prd_workflow)
        print("🧠 กำลังส่งข้อมูลให้ Qwen 3.5 ประมวลผล (กรุณารอสักครู่)...")
        final_state = await prd_workflow.ainvoke(mock_state)
        
        print("\n" + "="*50)
        print("🎉 การรันสำเร็จ! ผลลัพธ์ที่ได้จากแต่ละ Node:")
        print("="*50)
        
        # 3. เช็คผลลัพธ์ของ Node 1: Gatherer
        print("\n📋 [1/3] ผลลัพธ์การแปลงคำพูดเป็น Agile User Stories:")
        print(json.dumps(final_state.get("structured_requirements"), indent=2, ensure_ascii=False))
        
        # 4. เช็คผลลัพธ์ของ Node 2: Auditor
        print("\n🛡️ [2/3] ผลลัพธ์การตรวจสอบความปลอดภัยธนาคาร (Audit Result):")
        audit_res = final_state.get("audit_result", {})
        print(f"-> ผ่านเกณฑ์ความปลอดภัยทันทีหรือไม่? (is_valid): {audit_res.get('is_valid')}")
        print(f"-> หมวดหมู่ที่ผ่าน (passed_checks): {audit_res.get('passed_checks')}")
        print(f"-> หมวดหมู่ที่ตก/ต้องการข้อมูลเพิ่ม (failed_checks): {audit_res.get('failed_checks')}")
        
        if audit_res.get("clarification_questions"):
            print("❌ คำถามที่ Agent อยากถามผู้ใช้เพิ่มเพื่อความปลอดภัย:")
            print(json.dumps(audit_res.get("clarification_questions"), indent=2, ensure_ascii=False))
            print("\n💡 สถานะ: กราฟหยุดทำงานถูกต้องตามสเปก (Human-in-the-Loop) เพื่อรอคำตอบจากหน้าบ้าน")
        else:
            # 5. เช็คผลลัพธ์ของ Node 3: Architect (จะทำงานก็ต่อเมื่อผ่าน Audit เท่านั้น)
            print("\n📐 [3/3] เอกสาร PRD Markdown & ผังโครงสร้างแบบ Mermaid:")
            print("--- PRD Markdown (ตัวอย่าง) ---")
            print(final_state.get("prd_markdown")[:300] + "...\n[ตัดข้อความเพื่อให้สั้นลง]")
            print("\n--- Mermaid Diagram ---")
            print(final_state.get("mermaid_diagram"))
            print("\n💡 สถานะ: ข้อมูลสมบูรณ์แบบร้อยเปอร์เซ็นต์ ทะลุผ่านไปจนเจน PRD สำเร็จ!")

    except Exception as e:
        print(f"\n🚨 เกิดข้อผิดพลาดในระบบ: {str(e)}")

if __name__ == "__main__":
    # รันฟังก์ชัน Async
    asyncio.run(main())