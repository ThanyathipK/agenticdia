"""
Test script to verify database connection and general question handling.
"""
import asyncio
import sys
from app.config import settings
from app.database import engine, get_db
from app.semantic_service import detect_requirement_intent, generate_general_chat_response
from app.repository import ConversationMessageRepository

async def test_database_connection():
    """Test 1: Verify database connection works"""
    print("\n=== Test 1: Database Connection ===")
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.fetchone()
            print(f"✓ Database connection successful! Test query result: {row[0]}")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {str(e)}")
        return False

async def test_intent_detection():
    """Test 2: Verify intent detection works for general questions"""
    print("\n=== Test 2: Intent Detection ===")
    try:
        # Test general question
        result = await detect_requirement_intent("What is idempotency?", [])
        print(f"✓ Intent detection successful!")
        print(f"  Intent: {result.get('intent')}")
        print(f"  Confidence: {result.get('confidence')}")
        print(f"  Reason: {result.get('reason')}")
        
        if result.get('intent') == 'GENERAL_CHAT':
            print("✓ Correctly classified as GENERAL_CHAT")
            return True
        else:
            print(f"✗ Expected GENERAL_CHAT but got {result.get('intent')}")
            return False
    except Exception as e:
        print(f"✗ Intent detection failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def test_general_chat_response():
    """Test 3: Verify general chat response generation works"""
    print("\n=== Test 3: General Chat Response ===")
    try:
        project_context = {
            "project_name": "Test Project",
            "requirements": [],
            "user_stories": [],
            "acceptance_criteria": []
        }
        
        response = await generate_general_chat_response(
            raw_input="What is idempotency?",
            project_context=project_context,
            conversation_history=[]
        )
        
        print(f"✓ General chat response generated successfully!")
        print(f"  Response length: {len(response)} chars")
        print(f"  Response preview: {response[:200]}...")
        
        if response and len(response) > 0:
            return True
        else:
            print("✗ Response was empty")
            return False
    except Exception as e:
        print(f"✗ General chat response failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def test_conversation_history():
    """Test 4: Verify conversation history operations work"""
    print("\n=== Test 4: Conversation History ===")
    try:
        # Try to get conversation history (should work even if empty)
        # Use a valid UUID format for testing
        history = await ConversationMessageRepository.get_conversation_history("00000000-0000-0000-0000-000000000000")
        print(f"✓ Conversation history retrieval successful!")
        print(f"  Messages found: {len(history)}")
        return True
    except Exception as e:
        print(f"✗ Conversation history failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("=" * 60)
    print("Testing Database Connection & General Question Handling")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Database Connection", await test_database_connection()))
    results.append(("Intent Detection", await test_intent_detection()))
    results.append(("General Chat Response", await test_general_chat_response()))
    results.append(("Conversation History", await test_conversation_history()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! The fixes are working correctly.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)