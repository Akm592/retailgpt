from __future__ import annotations
from typing import Dict, Any

# ---------------------------------------------------------------------------
# Flat step graph — every key is a globally unique step ID.
# Transition targets are either another step ID or the reserved value "ESCALATE".
# "ESCALATE" triggers agent handover + AI summary generation.
# ---------------------------------------------------------------------------

FLOWS: Dict[str, Dict[str, Any]] = {

    # ── FLOW 0: Main Menu ────────────────────────────────────────────────────
    "main": {
        "render": {
            "render_type": "options",
            "message": "Hello! Welcome to RetailGPT Support. How can I help you today?",
            "options": [
                {"id": "order_status",          "label": "📦 What happened to my order?"},
                {"id": "cancel",                "label": "❌ I want to cancel my order"},
                {"id": "delayed",               "label": "⏱️ My order is delayed"},
                {"id": "items_issue",           "label": "🛍️ Issue with items delivered"},
                {"id": "quality_issue",         "label": "🔍 I have a quality issue"},
                {"id": "quantity_issue",        "label": "⚖️ Quantity issue with my food"},
                {"id": "delivery_instructions", "label": "🛵 Instructions to delivery partner"},
                {"id": "modify",                "label": "✏️ I want to modify items in my order"},
                {"id": "coupon",                "label": "🎟️ Coupon related query"},
                {"id": "payment",               "label": "💳 Payment & billing query"},
            ],
        },
        "transitions": {
            "order_status":          "flow_order_status",
            "cancel":                "flow_cancel_detect",
            "delayed":               "flow_delayed",
            "items_issue":           "flow_items_detect",
            "quality_issue":         "flow_quality_detect",
            "quantity_issue":        "flow_quantity",
            "delivery_instructions": "flow_delivery_instructions",
            "modify":                "flow_modify",
            "coupon":                "flow_coupon",
            "payment":               "flow_payment",
        },
    },

    # ── FLOW 1: Order Status ─────────────────────────────────────────────────
    "flow_order_status": {
        "render": {
            "render_type": "options",
            "message": "Sure, let me check your order status. Which category is your order?",
            "options": [
                {"id": "fb",          "label": "🍕 Food & Beverages (F&B)"},
                {"id": "fashion",     "label": "👗 Fashion & Apparel"},
                {"id": "electronics", "label": "💻 Electronics"},
            ],
        },
        "transitions": {
            "fb":          "flow_order_select_status_fb",
            "fashion":     "flow_order_select_status_fashion",
            "electronics": "flow_order_select_status_electronics",
        },
    },

    "flow_order_status_fb": {
        "render": {
            "render_type": "options",
            "message": "Your yummy food is on the way! 🚀 Expected to reach you by <time>.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    # ── FLOW 2: Cancel Order ─────────────────────────────────────────────────
    "flow_cancel_detect": {
        "render": {
            "render_type": "options",
            "message": "I can help with your cancellation. What type of order is it?",
            "options": [
                {"id": "fb",          "label": "🍕 Food & Beverages (F&B)"},
                {"id": "fashion",     "label": "👗 Fashion & Apparel"},
                {"id": "electronics", "label": "💻 Electronics"},
            ],
        },
        "transitions": {
            "fb":          "flow_order_select_cancel_fb",
            "fashion":     "flow_order_select_cancel_fashion",
            "electronics": "flow_order_select_cancel_electronics",
        },
    },

    "flow_cancel_fb": {
        "render": {
            "render_type": "options",
            "message": "Checking your cancellation window... Was your order placed within the last 30 seconds?",
            "options": [
                {"id": "yes", "label": "Yes, I just placed it"},
                {"id": "no",  "label": "No, it was placed earlier"},
            ],
        },
        "transitions": {
            "yes": "flow_cancel_fb_reason",
            "no":  "flow_cancel_elapsed",
        },
    },

    "flow_cancel_elapsed": {
        "render": {
            "render_type": "options",
            "message": "We regret to inform you that we won't be able to cancel the order as it has passed the allowed cancellation time.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_cancel_fb_reason": {
        "render": {
            "render_type": "options",
            "message": "Please select the reason for cancellation:",
            "options": [
                {"id": "duplicate",  "label": "I placed a duplicate order"},
                {"id": "add_items",  "label": "I forgot to add more items"},
                {"id": "price",      "label": "Getting better price elsewhere"},
                {"id": "wrong",      "label": "I placed a wrong order"},
                {"id": "not_avail",  "label": "I'm not available to pickup"},
            ],
        },
        "transitions": {
            "duplicate": "flow_cancel_done",
            "add_items": "flow_cancel_done",
            "price":     "flow_cancel_done",
            "wrong":     "flow_cancel_done",
            "not_avail": "flow_cancel_done",
        },
    },

    "flow_cancel_done": {
        "render": {
            "render_type": "options",
            "message": "Your order has been successfully cancelled. ✅",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_cancel_grocery_reason": {
        "render": {
            "render_type": "options",
            "message": "Please select the reason for cancellation:",
            "options": [
                {"id": "duplicate",  "label": "I placed a duplicate order"},
                {"id": "add_items",  "label": "I forgot to add more items"},
                {"id": "price",      "label": "Getting better price elsewhere"},
                {"id": "wrong",      "label": "I placed a wrong order"},
                {"id": "not_avail",  "label": "I'm not available to pickup"},
                {"id": "not_home",   "label": "I'm not at home"},
            ],
        },
        "transitions": {
            "duplicate": "flow_cancel_done",
            "add_items": "flow_cancel_done",
            "price":     "flow_cancel_done",
            "wrong":     "flow_cancel_done",
            "not_avail": "flow_cancel_reschedule",
            "not_home":  "flow_cancel_reschedule",
        },
    },

    "flow_cancel_reschedule": {
        "render": {
            "render_type": "options",
            "message": "Your order hasn't been picked up yet. Would you like to reschedule instead of cancelling?",
            "options": [
                {"id": "reschedule", "label": "Yes, reschedule my delivery"},
                {"id": "cancel",     "label": "No, cancel the order"},
            ],
        },
        "transitions": {
            "reschedule": "flow_cancel_rescheduled",
            "cancel":     "flow_cancel_done",
        },
    },

    "flow_cancel_rescheduled": {
        "render": {
            "render_type": "options",
            "message": "Please select your preferred delivery date & time from the available slots. Your delivery has been rescheduled! ✅",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    # ── FLOW 3: Order Delayed ────────────────────────────────────────────────
    "flow_delayed": {
        "render": {
            "render_type": "options",
            "message": "Let me check your delivery status...",
            "options": [
                {"id": "ontime", "label": "Order is still showing on time"},
                {"id": "late",   "label": "Order is genuinely late"},
            ],
        },
        "transitions": {
            "ontime": "flow_delayed_ontime",
            "late":   "flow_delayed_late",
        },
    },

    "flow_delayed_ontime": {
        "render": {
            "render_type": "options",
            "message": "Good news! Your order is on track and expected to reach you by <time>.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_delayed_late": {
        "render": {
            "render_type": "options",
            "message": "We are sorry your order is delayed. We are trying our best to get it to you early. Your order will reach you by <time>. Thanks for your patience and understanding!",
            "options": [
                {"id": "menu",  "label": "Yes, back to menu"},
                {"id": "agent", "label": "I want to speak with an agent"},
                {"id": "done",  "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "menu":  "main",
            "agent": "flow_delayed_agent",
            "done":  "flow_end",
        },
    },

    "flow_delayed_agent": {
        "render": {
            "render_type": "options",
            "message": "Connecting you to a live agent. The agent will contact the delivery partner and push for speedy delivery. If you are still unsatisfied, the agent may initiate a Delivery Fee Refund as a goodwill gesture.",
            "options": [
                {"id": "ok", "label": "Okay, I'll wait"},
            ],
        },
        "transitions": {
            "ok": "ESCALATE",
        },
    },

    # ── FLOW 4: Issues with Items Delivered ──────────────────────────────────
    "flow_items_detect": {
        "render": {
            "render_type": "options",
            "message": "I'm sorry to hear that! What type of order was it?",
            "options": [
                {"id": "fb",          "label": "🍕 Food & Beverages (F&B)"},
                {"id": "fashion",     "label": "👗 Fashion & Apparel"},
                {"id": "electronics", "label": "💻 Electronics"},
            ],
        },
        "transitions": {
            "fb":          "flow_order_select_items_fb",
            "fashion":     "flow_order_select_items_fashion",
            "electronics": "flow_order_select_items_electronics",
        },
    },

    "flow_items_fb": {
        "render": {
            "render_type": "options",
            "message": "Please select the issue:",
            "options": [
                {"id": "incorrect", "label": "❌ Incorrect items delivered"},
                {"id": "missing",   "label": "📦 Items are missing"},
            ],
        },
        "transitions": {
            "incorrect": "flow_items_fb_incorrect",
            "missing":   "flow_items_fb_missing",
        },
    },

    "flow_items_fb_incorrect": {
        "render": {
            "render_type": "upload",
            "message": "Please select the incorrectly delivered items from your order list. Then upload 3 photos 📷 of the incorrect items. (Mandatory)",
            "upload_config": {"required": True, "min_photos": 3, "video": False, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "incorrect_item",
        },
        "transitions": {
            "upload_complete": "flow_items_fb_incorrect_done",
        },
    },

    "flow_items_fb_incorrect_done": {
        "render": {
            "render_type": "options",
            "message": "Chat connected to live agent for verification. Once verified: Rs.<refund value> will be refunded to your source account in <N> days. An auto-email confirmation will be sent.",
            "options": [
                {"id": "ok", "label": "Okay, thank you"},
            ],
        },
        "transitions": {
            "ok": "ESCALATE",
        },
    },

    "flow_items_fb_missing": {
        "render": {
            "render_type": "upload",
            "message": "Please select the missing items from your order list. Then upload photos 📷 of the items you did receive. (Mandatory)",
            "upload_config": {"required": True, "min_photos": 2, "video": False, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "missing_item",
        },
        "transitions": {
            "upload_complete": "flow_items_fb_missing_done",
        },
    },

    "flow_items_fb_missing_done": {
        "render": {
            "render_type": "options",
            "message": "Live agent is verifying your claim. Once confirmed: Rs.<refund value> will be refunded to your source account in <N> days. An auto-email confirmation will be sent.",
            "options": [
                {"id": "ok", "label": "Okay, thank you"},
            ],
        },
        "transitions": {
            "ok": "ESCALATE",
        },
    },

    # ── FLOW 5: Quality Issue ────────────────────────────────────────────────
    "flow_quality_detect": {
        "render": {
            "render_type": "options",
            "message": "I'm sorry to hear about the quality issue! Which category is your order?",
            "options": [
                {"id": "fb",          "label": "🍕 Food & Beverages (F&B)"},
                {"id": "fashion",     "label": "👗 Fashion & Apparel"},
                {"id": "electronics", "label": "💻 Electronics"},
            ],
        },
        "transitions": {
            "fb":          "flow_order_select_quality_fb",
            "fashion":     "flow_order_select_quality_fashion",
            "electronics": "flow_order_select_quality_electronics",
        },
    },

    # F&B Quality
    "flow_quality_fb": {
        "render": {
            "render_type": "options",
            "message": "Please select the specific quality issue:",
            "options": [
                {"id": "stale",    "label": "Item(s) was stale"},
                {"id": "burnt",    "label": "Item was burnt / overcooked"},
                {"id": "taste",    "label": "Poor taste"},
                {"id": "spillage", "label": "Package / spillage issue"},
            ],
        },
        "transitions": {
            "stale":    "flow_quality_fb_upload",
            "burnt":    "flow_quality_fb_upload",
            "taste":    "flow_quality_fb_upload",
            "spillage": "flow_quality_fb_upload",
        },
    },

    "flow_quality_fb_upload": {
        "render": {
            "render_type": "upload",
            "message": "Please upload 3 pictures + 1 video 📷🎥 of the items with issues. (Mandatory)",
            "upload_config": {"required": True, "min_photos": 3, "video": True, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "quality_issue_fb",
        },
        "transitions": {
            "upload_complete": "flow_quality_fb_done",
        },
    },

    "flow_quality_fb_done": {
        "render": {
            "render_type": "options",
            "message": "Connecting to live agent for verification. Once verified: <refund value> will be refunded to your source account in <N> days. A ticket has been sent to the retailer for acknowledgement.",
            "options": [
                {"id": "ok", "label": "Okay, thank you"},
            ],
        },
        "transitions": {
            "ok": "ESCALATE",
        },
    },

    # Fashion Quality
    "flow_quality_fashion": {
        "render": {
            "render_type": "options",
            "message": "Please select the quality issue with your fashion item:",
            "options": [
                {"id": "wrong_size",      "label": "Incorrect size received"},
                {"id": "size_fit",        "label": "Size selected doesn't fit me"},
                {"id": "wrong_colour",    "label": "Colour ordered & received is different"},
                {"id": "change_colour",   "label": "Not happy with colour, wish to change"},
                {"id": "dirty",           "label": "Product has dirt / spoiled"},
                {"id": "expectations",    "label": "Product not up to expectations"},
                {"id": "wrong_brand",     "label": "Ordered brand not received"},
                {"id": "packing_damaged", "label": "Packing damaged, product is good"},
                {"id": "both_damaged",    "label": "Product & packing both damaged"},
            ],
        },
        "transitions": {
            "wrong_size":      "flow_quality_fashion_refund",
            "size_fit":        "flow_quality_fashion_refund",
            "wrong_colour":    "flow_quality_fashion_refund",
            "change_colour":   "flow_quality_fashion_refund",
            "dirty":           "flow_quality_fashion_refund",
            "expectations":    "flow_quality_fashion_expectations",
            "wrong_brand":     "flow_quality_fashion_refund",
            "packing_damaged": "flow_quality_fashion_packing",
            "both_damaged":    "flow_quality_fashion_refund",
        },
    },

    "flow_quality_fashion_refund": {
        "render": {
            "render_type": "upload",
            "message": "Please upload 3 pictures 📷 of the item. (Mandatory). Agent will verify. Refund / Replacement will be processed once verified. <Refund value / replacement> will be settled in <N> days.",
            "upload_config": {"required": True, "min_photos": 3, "video": False, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "quality_issue_fashion",
        },
        "transitions": {
            "upload_complete": "flow_end",
        },
    },

    "flow_quality_fashion_expectations": {
        "render": {
            "render_type": "upload",
            "message": "Please upload 3 pictures 📷 of the item. (Mandatory). Agent will verify and process a Refund. <Refund value> will be refunded in <N> days.",
            "upload_config": {"required": True, "min_photos": 3, "video": False, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "quality_issue_fashion",
        },
        "transitions": {
            "upload_complete": "flow_end",
        },
    },

    "flow_quality_fashion_packing": {
        "render": {
            "render_type": "upload",
            "message": "Please upload 3 pictures 📷 of the damaged packaging. (Mandatory). Ticket raised with Delivery Partner — must acknowledge within 24hrs. Delivery Charge Refund will be processed.",
            "upload_config": {"required": True, "min_photos": 3, "video": False, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "quality_issue_fashion_packing",
        },
        "transitions": {
            "upload_complete": "flow_end",
        },
    },

    # Electronics Quality
    "flow_quality_electronics": {
        "render": {
            "render_type": "options",
            "message": "Please select the quality issue with your electronics item:",
            "options": [
                {"id": "not_working",     "label": "Product not working / damaged"},
                {"id": "damaged_working", "label": "Product damaged but working"},
                {"id": "wrong_colour",    "label": "Colour ordered & received is different"},
                {"id": "dirty",           "label": "Product has dirt / spoiled"},
                {"id": "expectations",    "label": "Product not up to expectations"},
                {"id": "wrong_brand",     "label": "Ordered brand not received"},
                {"id": "packing_damaged", "label": "Packing damaged, product is good"},
            ],
        },
        "transitions": {
            "not_working":     "flow_quality_electronics_refund",
            "damaged_working": "flow_quality_electronics_refund",
            "wrong_colour":    "flow_quality_electronics_refund",
            "dirty":           "flow_quality_electronics_refund",
            "expectations":    "flow_quality_electronics_refund",
            "wrong_brand":     "flow_quality_electronics_refund",
            "packing_damaged": "flow_quality_electronics_packing",
        },
    },

    "flow_quality_electronics_refund": {
        "render": {
            "render_type": "upload",
            "message": "Please upload 3 pictures + 1 video 📷🎥 of the item. (Mandatory). Agent will verify. Refund / Replacement will be processed. <Refund value / replacement> will be settled in <N> days.",
            "upload_config": {"required": True, "min_photos": 3, "video": True, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "quality_issue_electronics",
        },
        "transitions": {
            "upload_complete": "flow_end",
        },
    },

    "flow_quality_electronics_packing": {
        "render": {
            "render_type": "upload",
            "message": "Please upload 3 pictures + 1 video 📷🎥 of the damaged packaging. (Mandatory). Ticket raised with Delivery Partner — must acknowledge within 24hrs. Delivery Charge Refund will be processed.",
            "upload_config": {"required": True, "min_photos": 3, "video": True, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "quality_issue_electronics_packing",
        },
        "transitions": {
            "upload_complete": "flow_end",
        },
    },

    # ── FLOW 6: Quantity Issue ────────────────────────────────────────────────
    "flow_quantity": {
        "render": {
            "render_type": "options",
            "message": "Please select the items with the quantity issue from your order. Now select the specific issue:",
            "options": [
                {"id": "less_vs_others", "label": "Quantity less vs other restaurants"},
                {"id": "expected_more",  "label": "Expected more for the price paid"},
                {"id": "more_received",  "label": "Quantity was more than expected"},
            ],
        },
        "transitions": {
            "less_vs_others": "flow_quantity_response",
            "expected_more":  "flow_quantity_response",
            "more_received":  "flow_quantity_response",
        },
    },

    "flow_quantity_response": {
        "render": {
            "render_type": "options",
            "message": "We are sorry you were not satisfied with the Quantity. We will share your feedback with the Restaurant. We hope to meet your expectations in future orders.",
            "options": [
                {"id": "menu",  "label": "Yes, back to menu"},
                {"id": "agent", "label": "I want to speak with an agent"},
                {"id": "done",  "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "menu":  "main",
            "agent": "flow_quantity_agent",
            "done":  "flow_end",
        },
    },

    "flow_quantity_agent": {
        "render": {
            "render_type": "options",
            "message": "Connecting to live agent. The agent will apologize and assure better future service. If you are completely dissatisfied, the agent may offer a goodwill coupon tagged for quantity issue.",
            "options": [
                {"id": "ok", "label": "Okay, I'll wait"},
            ],
        },
        "transitions": {
            "ok": "ESCALATE",
        },
    },

    # ── FLOW 7: Delivery Instructions ────────────────────────────────────────
    "flow_delivery_instructions": {
        "render": {
            "render_type": "options",
            "message": "Sure! What instruction would you like to give the delivery partner? (Available until they reach your location)",
            "options": [
                {"id": "no_bell",      "label": "Avoid ringing the bell 🔕"},
                {"id": "door",         "label": "Leave items at the door 🚪"},
                {"id": "no_call",      "label": "Avoid calling me 📵"},
                {"id": "directions",   "label": "Give directions to reach me 📍"},
                {"id": "neighbour",    "label": "Leave at neighbour's place 🏠"},
            ],
        },
        "transitions": {
            "no_bell":    "flow_di_simple",
            "door":       "flow_di_simple",
            "no_call":    "flow_di_simple",
            "directions": "flow_di_directions",
            "neighbour":  "flow_di_neighbour",
        },
    },

    "flow_di_simple": {
        "render": {
            "render_type": "options",
            "message": "Your instruction has been noted and passed to the delivery partner with a timestamp. ✅",
            "options": [
                {"id": "more_instr", "label": "Yes, more instructions"},
                {"id": "done",       "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more_instr": "flow_delivery_instructions",
            "done":       "flow_end",
        },
    },

    "flow_di_directions": {
        "render": {
            "render_type": "text_input",
            "message": "Please type your directions below — they'll be passed directly to the delivery partner.",
        },
        "transitions": {
            "*": "flow_di_simple",
        },
    },

    "flow_di_neighbour": {
        "render": {
            "render_type": "text_input",
            "message": "Please provide your neighbour's Name, Contact Number, and Door Number. These will be shared with the delivery partner.",
        },
        "transitions": {
            "*": "flow_di_simple",
        },
    },

    # ── FLOW 8: Modify Order ──────────────────────────────────────────────────
    "flow_modify": {
        "render": {
            "render_type": "options",
            "message": "We regret to inform you that you will not be able to make changes to confirmed express delivery orders.",
            "options": [
                {"id": "menu", "label": "Yes, back to menu"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "menu": "main",
            "done": "flow_end",
        },
    },

    # ── FLOW 9: Coupon Query ──────────────────────────────────────────────────
    "flow_coupon": {
        "render": {
            "render_type": "options",
            "message": "I can help with your coupon query! What is the issue?",
            "options": [
                {"id": "find",   "label": "I'm unable to find my coupon"},
                {"id": "apply",  "label": "I'm unable to apply my coupon"},
                {"id": "forgot", "label": "I forgot to apply my coupon"},
            ],
        },
        "transitions": {
            "find":   "flow_coupon_find",
            "apply":  "flow_coupon_apply",
            "forgot": "flow_coupon_forgot",
        },
    },

    "flow_coupon_find": {
        "render": {
            "render_type": "options",
            "message": "You can view available coupons by going to the APPLY COUPON section on the cart page while placing your order.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_coupon_apply": {
        "render": {
            "render_type": "options",
            "message": "Please check if you have adhered to all the coupon's terms and conditions. Choose your coupon in the APPLY COUPON section and click +MORE to review all T&Cs.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_coupon_forgot": {
        "render": {
            "render_type": "options",
            "message": "It looks like you missed to apply your coupon. No worries! Your coupon is still available and waiting for you. Simply apply it to your next order and enjoy your savings.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    # ── FLOW 10: Payment & Billing ────────────────────────────────────────────
    "flow_payment": {
        "render": {
            "render_type": "options",
            "message": "I can help with payment & billing! Please select your query:",
            "options": [
                {"id": "refund",  "label": "I want to know my refund status"},
                {"id": "failure", "label": "I have a payment failure issue"},
                {"id": "invoice", "label": "I want invoice for this order"},
                {"id": "bill",    "label": "I have a bill related issue"},
                {"id": "coupon",  "label": "My coupon didn't work as expected"},
            ],
        },
        "transitions": {
            "refund":  "flow_payment_refund",
            "failure": "flow_payment_failure",
            "invoice": "flow_payment_invoice",
            "bill":    "flow_payment_bill",
            "coupon":  "flow_payment_coupon",
        },
    },

    "flow_payment_refund": {
        "render": {
            "render_type": "options",
            "message": "Checking your refund status... What is the current status?",
            "options": [
                {"id": "processed",   "label": "Refund has been processed"},
                {"id": "processing",  "label": "Refund is still being processed"},
                {"id": "none_raised", "label": "No refund request was raised"},
            ],
        },
        "transitions": {
            "processed":   "flow_payment_refund_done",
            "processing":  "flow_payment_refund_processing",
            "none_raised": "flow_payment_refund_none",
        },
    },

    "flow_payment_refund_done": {
        "render": {
            "render_type": "options",
            "message": "Your refund has been processed and the amount was settled to your source account on <date>. Kindly check your bank / card account.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_payment_refund_processing": {
        "render": {
            "render_type": "options",
            "message": "Your refund is being processed. You will receive the refund amount to your source account in 3-4 business days from the day of the request.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_payment_refund_none": {
        "render": {
            "render_type": "options",
            "message": "We don't have any refund request against this order. Is the refund eligibility window still open?",
            "options": [
                {"id": "yes_raise", "label": "Yes, raise a refund request now"},
                {"id": "expired",   "label": "No, eligibility window has elapsed"},
            ],
        },
        "transitions": {
            "yes_raise": "flow_payment_raise_refund",
            "expired":   "flow_payment_refund_expired",
        },
    },

    # Cross-flow: branches back into other flows
    "flow_payment_raise_refund": {
        "render": {
            "render_type": "options",
            "message": "Please select the reason for your refund request:",
            "options": [
                {"id": "delayed",  "label": "My order was delayed"},
                {"id": "items",    "label": "Items were missing / incorrect"},
                {"id": "quality",  "label": "I had quality issues"},
            ],
        },
        "transitions": {
            "delayed": "flow_delayed",
            "items":   "flow_items_detect",
            "quality": "flow_quality_detect",
        },
    },

    "flow_payment_refund_expired": {
        "render": {
            "render_type": "options",
            "message": "We regret to inform you that your timeline to raise a refund request has expired.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_payment_failure": {
        "render": {
            "render_type": "options",
            "message": "We are sorry about the payment failure. Connecting you with a live agent for immediate assistance.",
            "options": [
                {"id": "ok", "label": "Yes, connect me to an agent"},
            ],
        },
        "transitions": {
            "ok": "ESCALATE",
        },
    },

    "flow_payment_invoice": {
        "render": {
            "render_type": "options",
            "message": "Here is the link to download your invoice: <Invoice Download Link>. You can also download it from your Order History page. We have also emailed the invoice to your registered email id.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_payment_bill": {
        "render": {
            "render_type": "options",
            "message": "We will be happy to assist you. Please wait while we connect you with our Customer Success Executive. The agent will go through your order details, menu, and pricing. If unresolved, a ticket will be created and a supervisor will provide resolution within 24-48 hours.",
            "options": [
                {"id": "ok", "label": "Okay, I'll wait for the agent"},
            ],
        },
        "transitions": {
            "ok": "ESCALATE",
        },
    },

    "flow_payment_coupon": {
        "render": {
            "render_type": "options",
            "message": "Connecting you with a Customer Success Executive. The agent will check your order and coupon T&Cs. If it is a valid claim, a ticket will be assigned to the Program team (offer-related) or Technology team (technical). Resolution within 24-48 hours.",
            "options": [
                {"id": "ok", "label": "Okay, I'll wait"},
            ],
        },
        "transitions": {
            "ok": "ESCALATE",
        },
    },

    # ── Order Select steps ────────────────────────────────────────────────────
    # These steps have fetch_orders=True so app.py will call the orders API
    # and inject the returned past orders as suggestion buttons.
    # capture_as_order_id=True means the selected option_id is saved to ctx.order_id.

    "flow_order_select_status_fb": {
        "render": {
            "render_type": "options",
            "message": "Please select the order you'd like to check:",
            "options": [],
            "fetch_orders": True,
            "order_category": "fb",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_order_status_fb"},
    },


    "flow_order_select_cancel_fb": {
        "render": {
            "render_type": "options",
            "message": "Please select the order you'd like to cancel:",
            "options": [],
            "fetch_orders": True,
            "order_category": "fb",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_cancel_fb"},
    },

    "flow_order_select_items_fb": {
        "render": {
            "render_type": "options",
            "message": "Please select the order with the item issue:",
            "options": [],
            "fetch_orders": True,
            "order_category": "fb",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_items_fb"},
    },

    "flow_order_select_quality_fb": {
        "render": {
            "render_type": "options",
            "message": "Please select the order with the quality issue:",
            "options": [],
            "fetch_orders": True,
            "order_category": "fb",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_quality_fb"},
    },

    "flow_order_select_quality_fashion": {
        "render": {
            "render_type": "options",
            "message": "Please select the order with the quality issue:",
            "options": [],
            "fetch_orders": True,
            "order_category": "fashion",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_quality_fashion"},
    },

    "flow_order_select_quality_electronics": {
        "render": {
            "render_type": "options",
            "message": "Please select the order with the quality issue:",
            "options": [],
            "fetch_orders": True,
            "order_category": "electronics",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_quality_electronics"},
    },

    # ── Order Select: Fashion & Electronics (status, cancel, items) ──────────

    "flow_order_select_status_fashion": {
        "render": {
            "render_type": "options",
            "message": "Please select the order you'd like to check:",
            "options": [],
            "fetch_orders": True,
            "order_category": "fashion",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_order_status_fashion"},
    },

    "flow_order_select_status_electronics": {
        "render": {
            "render_type": "options",
            "message": "Please select the order you'd like to check:",
            "options": [],
            "fetch_orders": True,
            "order_category": "electronics",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_order_status_electronics"},
    },

    "flow_order_select_cancel_fashion": {
        "render": {
            "render_type": "options",
            "message": "Please select the order you'd like to cancel:",
            "options": [],
            "fetch_orders": True,
            "order_category": "fashion",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_cancel_fashion"},
    },

    "flow_order_select_cancel_electronics": {
        "render": {
            "render_type": "options",
            "message": "Please select the order you'd like to cancel:",
            "options": [],
            "fetch_orders": True,
            "order_category": "electronics",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_cancel_electronics"},
    },

    "flow_order_select_items_fashion": {
        "render": {
            "render_type": "options",
            "message": "Please select the order with the item issue:",
            "options": [],
            "fetch_orders": True,
            "order_category": "fashion",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_items_fashion"},
    },

    "flow_order_select_items_electronics": {
        "render": {
            "render_type": "options",
            "message": "Please select the order with the item issue:",
            "options": [],
            "fetch_orders": True,
            "order_category": "electronics",
            "capture_as_order_id": True,
        },
        "transitions": {"*": "flow_items_electronics"},
    },

    # ── Order Status: Fashion & Electronics ───────────────────────────────────

    "flow_order_status_fashion": {
        "render": {
            "render_type": "options",
            "message": "Your order has been <Received/Packed/Shipped>. Expected delivery by <today/tomorrow/date, time>.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    "flow_order_status_electronics": {
        "render": {
            "render_type": "options",
            "message": "Your order has been <Received/Packed/Shipped>. Expected delivery by <today/tomorrow/date, time>.",
            "options": [
                {"id": "more", "label": "Yes, I have more questions"},
                {"id": "done", "label": "No, I'm good 👍"},
            ],
        },
        "transitions": {
            "more": "main",
            "done": "flow_end",
        },
    },

    # ── Cancel: Fashion & Electronics ─────────────────────────────────────────

    "flow_cancel_fashion": {
        "render": {
            "render_type": "options",
            "message": "Is the order still within the cancellation time frame?",
            "options": [
                {"id": "yes", "label": "Yes, within the window"},
                {"id": "no",  "label": "No, time has elapsed"},
            ],
        },
        "transitions": {
            "yes": "flow_cancel_grocery_reason",
            "no":  "flow_cancel_elapsed",
        },
    },

    "flow_cancel_electronics": {
        "render": {
            "render_type": "options",
            "message": "Is the order still within the cancellation time frame?",
            "options": [
                {"id": "yes", "label": "Yes, within the window"},
                {"id": "no",  "label": "No, time has elapsed"},
            ],
        },
        "transitions": {
            "yes": "flow_cancel_grocery_reason",
            "no":  "flow_cancel_elapsed",
        },
    },

    # ── Items Issue: Fashion & Electronics ────────────────────────────────────

    "flow_items_fashion": {
        "render": {
            "render_type": "options",
            "message": "What is the issue with the items delivered?",
            "options": [
                {"id": "incorrect", "label": "❌ Incorrect items delivered"},
                {"id": "missing",   "label": "📦 Items are missing"},
            ],
        },
        "transitions": {
            "incorrect": "flow_items_fashion_ticket",
            "missing":   "flow_items_fashion_ticket",
        },
    },

    "flow_items_fashion_ticket": {
        "render": {
            "render_type": "upload",
            "message": "Please upload 3 photos 📷 of the items received. (Mandatory). Ticket #XXXX created — resolution within 48 hours. Retailer must respond within 24 hours. Replacement / Refund will be processed after confirmation. Auto-email will be sent.",
            "upload_config": {"required": True, "min_photos": 3, "video": False, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "incorrect_or_missing_item_fashion",
        },
        "transitions": {
            "upload_complete": "flow_end",
        },
    },

    "flow_items_electronics": {
        "render": {
            "render_type": "options",
            "message": "What is the issue with the items delivered?",
            "options": [
                {"id": "incorrect", "label": "❌ Incorrect items delivered"},
                {"id": "missing",   "label": "📦 Items are missing"},
            ],
        },
        "transitions": {
            "incorrect": "flow_items_electronics_ticket",
            "missing":   "flow_items_electronics_ticket",
        },
    },

    "flow_items_electronics_ticket": {
        "render": {
            "render_type": "upload",
            "message": "Please upload 3 photos 📷 of the items received. (Mandatory). Ticket #XXXX created — resolution within 48 hours. Retailer must respond within 24 hours. Replacement / Refund will be processed after confirmation. Auto-email will be sent.",
            "upload_config": {"required": True, "min_photos": 3, "video": False, "max_size_mb": 20},
            "ticket_raised": True,
            "issue_type": "incorrect_or_missing_item_electronics",
        },
        "transitions": {
            "upload_complete": "flow_end",
        },
    },

    # ── End: Survey ───────────────────────────────────────────────────────────
    "flow_end": {
        "render": {
            "render_type": "options",
            "message": "Thank you for contacting RetailGPT Support! We were happy to assist you today. Have a Great Day! 😊 Would you like to rate your support experience?",
            "options": [
                {"id": "5", "label": "⭐⭐⭐⭐⭐ Excellent"},
                {"id": "4", "label": "⭐⭐⭐⭐ Good"},
                {"id": "3", "label": "⭐⭐⭐ Average"},
                {"id": "2", "label": "⭐⭐ Poor"},
                {"id": "1", "label": "⭐ Very Poor"},
            ],
        },
        "transitions": {
            "5": "flow_rated",
            "4": "flow_rated",
            "3": "flow_rated",
            "2": "flow_rated",
            "1": "flow_rated",
        },
    },

    "flow_rated": {
        "render": {
            "render_type": "options",
            "message": "Thank you for your feedback! Your rating has been recorded. Have a wonderful day! 👋",
            "options": [
                {"id": "restart", "label": "🔄 Start new conversation"},
            ],
        },
        "transitions": {
            "restart": "main",
        },
    },
}


# ---------------------------------------------------------------------------
# Intent → initial step ID mapping (replaces INTENT_TO_FLOW)
# When category is known, route directly to the category-specific step.
# ---------------------------------------------------------------------------
from engine.nlu import RetailIntent, RetailCategory

INTENT_TO_STEP = {
    RetailIntent.TRACK_ORDER: {
        RetailCategory.FB:          "flow_order_status_fb",
        RetailCategory.FASHION:     "flow_order_status_fashion",
        RetailCategory.ELECTRONICS: "flow_order_status_electronics",
        RetailCategory.UNKNOWN:     "flow_order_status",
        "*":                        "flow_order_status",
    },
    RetailIntent.CANCEL_ORDER: {
        RetailCategory.FB:          "flow_cancel_fb",
        RetailCategory.FASHION:     "flow_cancel_fashion",
        RetailCategory.ELECTRONICS: "flow_cancel_electronics",
        RetailCategory.UNKNOWN:     "flow_cancel_detect",
        "*":                        "flow_cancel_detect",
    },
    RetailIntent.DELAYED_ORDER:  {"*": "flow_delayed"},
    RetailIntent.MISSING_ITEM:   {"*": "flow_items_detect"},
    RetailIntent.WRONG_ITEM:     {"*": "flow_items_detect"},
    RetailIntent.QUALITY_ISSUE: {
        RetailCategory.FB:          "flow_quality_fb",
        RetailCategory.FASHION:     "flow_quality_fashion",
        RetailCategory.ELECTRONICS: "flow_quality_electronics",
        RetailCategory.UNKNOWN:     "flow_quality_detect",
        "*":                        "flow_quality_detect",
    },
    RetailIntent.QUANTITY_ISSUE: {"*": "flow_quantity"},
    RetailIntent.DELIVERY_INSTR: {"*": "flow_delivery_instructions"},
    RetailIntent.MODIFY_ORDER:   {"*": "flow_modify"},
    RetailIntent.COUPON_QUERY:   {"*": "flow_coupon"},
    RetailIntent.PAYMENT_QUERY:  {"*": "flow_payment"},
    RetailIntent.REQUEST_AGENT:  {"*": "ESCALATE"},
    RetailIntent.UNKNOWN:        {"*": "main"},
}
