# Queue Notification Feature (PRIS-84) Manual Test Cases

## 📋 Feature Overview

**Feature Name**: Browser Queue Notification System  
**Jira Ticket**: PRIS-84  
**Commit Records**: 
- `a7588c2` - Add browser queue notifications
- `faecce5` - Reset notification flags and optimize mobile experience
- `72c5a34` - Merge PR #12

**Feature Description**:  
When users are waiting in the robot control queue, the system sends browser notifications when their position approaches their turn, preventing them from missing their control opportunity.

---

## 🎯 Test Strategy Analysis

### Core Features

#### 1. **Notification Permission Management** 🔐
- Desktop: Shows permission request prompt after joining queue
- Mobile: Does not show permission request prompt (due to inconsistent browser support)
- Permission prompt can be closed
- Clicking "Enable" button triggers native browser permission request

#### 2. **Notification Trigger Timing** ⏰
- **Position #6**: Send first notification "You're at position 6 in the queue!"
- **Position #2**: Send second notification "You're at position 2 in the queue!"
- Notifications only sent when permission is granted

#### 3. **State Management** 🔄
- Use `hasSentFirstNotificationRef` and `hasSentSecondNotificationRef` to prevent duplicate sends
- Reset notification flags when user leaves queue
- Reset notification flags when user activates control
- Fast Track does not cause duplicate notifications

#### 4. **Notification Content** 💬
- Title: Position reminder
- Content: Guides user to return to app
- Icon: PrismaX logo (favicon.svg)
- Auto-close time: 12 seconds

---

## 🧪 Test Environment Requirements

### Test Accounts
- **Amplifier Member**: For standard testing
- **Innovator Member**: For Fast Track testing
- **Explorer Member**: For upgrade prompt testing

### Test Robots
- `arm1` - Primary test robot
- `arm2` - Partner ARM (requires invitation code)
- `arm3` - Optional test robot

### Test Browsers
- ✅ **Chrome 120+** (Desktop + Mobile)
- ✅ **Firefox 120+** (Desktop)
- ✅ **Safari 17+** (Desktop + iOS)
- ✅ **Edge 120+** (Desktop)

### Test Devices
- **Desktop**: Windows 10/11, macOS Ventura+, Ubuntu 22.04+
- **Mobile**: iOS 17+, Android 13+

### Test Environment URLs
- **Dev Environment**: http://localhost:3000
- **QA Environment**: https://qa.prismax.ai
- **Staging Environment**: https://staging.prismax.ai

---

## 📝 Test Cases

---

### **Test Module A: Notification Permission Request - Desktop**

---

#### **Case QN-M-001: Desktop First Join Queue Shows Permission Prompt**

**Priority**: P0 🔴  
**Test Type**: Functional Testing  
**Estimated Time**: 3 minutes

**Preconditions**:
1. Using desktop browser (Chrome/Firefox/Safari/Edge)
2. Browser viewport width > 1000px
3. Browser notification permission is "default" (not set)
4. Logged in with test account (Amplifier Member)
5. On TeleOp page with robot selected (e.g. arm1)

**Test Steps**:
1. Click "Enter Live Control" button in queue panel
2. Wait for successful queue join (shows "You are now #X in the queue" message)
3. Observe the top area of queue panel

**Expected Results**:
- ✅ Light gray notification permission prompt appears at top of queue panel
- ✅ Prompt contains text: "🔔 Enable notifications to get alerts on your position in the queue."
- ✅ Prompt contains green "Enable" button
- ✅ Prompt has close button (X icon) in top right corner
- ✅ Prompt styling is elegant and follows PrismaX design standards

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-002: Clicking Enable Button Triggers Permission Request**

**Priority**: P0 🔴  
**Test Type**: Functional Testing  
**Estimated Time**: 3 minutes

**Preconditions**:
1. Completed QN-M-001, permission prompt is displayed
2. Browser notification permission is "default"

**Test Steps**:
1. Click green "Enable" button in permission prompt
2. Observe native browser permission request popup
3. Click "Allow" in native browser popup
4. Observe page feedback

**Expected Results**:
- ✅ Browser displays native notification permission request popup
- ✅ Popup asks whether to allow prismax.ai to send notifications
- ✅ After allowing, permission prompt automatically disappears
- ✅ Page shows green success message: "Notifications enabled! We'll send you two alerts before you're at position 5 and then 1..."
- ✅ Success message displays for about 10 seconds then auto-dismisses

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-003: Clicking Close Button Hides Permission Prompt**

**Priority**: P1 🟠  
**Test Type**: Functional Testing  
**Estimated Time**: 2 minutes

**Preconditions**:
1. Completed QN-M-001, permission prompt is displayed
2. Have not clicked Enable button

**Test Steps**:
1. Click X close button in top right corner of permission prompt
2. Observe permission prompt state

**Expected Results**:
- ✅ Permission prompt immediately disappears
- ✅ Does not trigger native browser permission request
- ✅ No error messages displayed
- ✅ Queue functionality operates normally

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-004: Permission Prompt Disappears After Denying**

**Priority**: P1 🟠  
**Test Type**: Functional Testing  
**Estimated Time**: 3 minutes

**Preconditions**:
1. Completed QN-M-001, permission prompt is displayed
2. Browser notification permission is "default"

**Test Steps**:
1. Click green "Enable" button in permission prompt
2. Click "Block" / "Deny" in native browser permission request popup
3. Observe page state

**Expected Results**:
- ✅ Permission prompt immediately disappears
- ✅ No error messages displayed
- ✅ Queue functionality operates normally
- ✅ Will not receive browser notifications (verify in subsequent tests)

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-005: No Prompt Displayed When Permission Already Granted**

**Priority**: P0 🔴  
**Test Type**: Functional Testing  
**Estimated Time**: 3 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission already set to "granted" (allowed)
3. Logged in with test account

**Test Steps**:
1. Select robot on TeleOp page
2. Click "Enter Live Control" button to join queue
3. Observe top of queue panel

**Expected Results**:
- ✅ No notification permission prompt displayed
- ✅ Directly shows queue status
- ✅ System ready to send notifications at appropriate positions

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-006: No Prompt Displayed When Permission Already Denied**

**Priority**: P1 🟠  
**Test Type**: Functional Testing  
**Estimated Time**: 3 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission already set to "denied" (blocked)
3. Logged in with test account

**Test Steps**:
1. Select robot on TeleOp page
2. Click "Enter Live Control" button to join queue
3. Observe top of queue panel

**Expected Results**:
- ✅ No notification permission prompt displayed
- ✅ Directly shows queue status
- ✅ Queue functionality operates normally (does not affect core features)

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

### **Test Module B: Notification Permission Request - Mobile**

---

#### **Case QN-M-007: Mobile Join Queue Does Not Show Permission Prompt**

**Priority**: P0 🔴  
**Test Type**: Functional Testing  
**Estimated Time**: 3 minutes

**Preconditions**:
1. Using mobile device browser (iOS Safari / Chrome, Android Chrome)
2. Or desktop browser simulating mobile viewport (width < 1000px)
3. Browser notification permission is "default"
4. Logged in with test account

**Test Steps**:
1. Select robot on TeleOp page
2. Click "Enter Live Control" button to join queue
3. Observe top of queue panel and entire page

**Expected Results**:
- ✅ No notification permission prompt displayed
- ✅ Directly shows queue status and position information
- ✅ Does not trigger any permission requests
- ✅ Queue functionality operates normally

**Rationale**: Mobile browsers have inconsistent support for notification API, avoiding user confusion

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

### **Test Module C: Notification Trigger - Position #6**

---

#### **Case QN-M-008: First Notification Sent When Queue Position Reaches #6**

**Priority**: P0 🔴  
**Test Type**: Functional Testing  
**Estimated Time**: 10-15 minutes (requires queue wait)

**Preconditions**:
1. Using desktop browser (Chrome recommended)
2. Browser notification permission already set to "granted"
3. Logged in with test account
4. Queue has enough users (at least 6 people)

**Test Steps**:
1. Select robot on TeleOp page and join queue
2. Record current queue position (e.g. position #10)
3. Wait for queue to move forward to position #6
4. Observe browser notification

**Expected Results**:
- ✅ When position reaches #6, immediately receive browser notification
- ✅ Notification title: "You're at position 6 in the queue!"
- ✅ Notification content: "It's almost your turn! Please continue to monitor the queue status."
- ✅ Notification displays PrismaX icon (favicon.svg)
- ✅ Notification displays for about 12 seconds then auto-closes
- ✅ Clicking notification focuses PrismaX tab

**Test Tips**:
- If insufficient queue users, can use multiple test accounts to quickly fill queue
- Or wait for users to naturally leave queue to move position forward

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-009: Position #6 Notification Content Accuracy Verification**

**Priority**: P1 🟠  
**Test Type**: Functional Testing  
**Estimated Time**: Refer to QN-M-008

**Preconditions**:
1. Same as QN-M-008
2. Prepare screenshot tool

**Test Steps**:
1. Execute steps from QN-M-008
2. When receiving position #6 notification, immediately take screenshot
3. Carefully check every detail of notification

**Expected Results**:
- ✅ Notification title accurately displays: "You're at position 6 in the queue!"
- ✅ Notification body accurately displays: "It's almost your turn! Please continue to monitor the queue status."
- ✅ Notification icon is PrismaX logo (not default browser icon)
- ✅ Notification badge is also PrismaX logo
- ✅ Text is clear and readable, no spelling errors
- ✅ Notification format follows OS style (Windows/macOS)

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

### **Test Module D: Notification Trigger - Position #2**

---

#### **Case QN-M-010: Second Notification Sent When Queue Position Reaches #2**

**Priority**: P0 🔴  
**Test Type**: Functional Testing  
**Estimated Time**: 15-20 minutes (requires queue wait)

**Preconditions**:
1. Using desktop browser (Chrome recommended)
2. Browser notification permission already set to "granted"
3. Logged in with test account
4. Already received position #6 notification (QN-M-008 passed)

**Test Steps**:
1. Continue waiting for queue to move forward
2. When position moves from #3 to #2
3. Observe browser notification

**Expected Results**:
- ✅ When position reaches #2, immediately receive browser notification
- ✅ Notification title: "You're at position 2 in the queue!"
- ✅ Notification content: "You're up next! There is one user ahead of you. Please return to the app."
- ✅ Notification displays PrismaX icon
- ✅ Notification displays for about 12 seconds then auto-closes
- ✅ This notification is independent from position #6 notification (different reminder)

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-011: Position #2 Notification Content Accuracy Verification**

**Priority**: P1 🟠  
**Test Type**: Functional Testing  
**Estimated Time**: Refer to QN-M-010

**Preconditions**:
1. Same as QN-M-010
2. Prepare screenshot tool

**Test Steps**:
1. Execute steps from QN-M-010
2. When receiving position #2 notification, immediately take screenshot
3. Carefully check every detail of notification

**Expected Results**:
- ✅ Notification title accurately displays: "You're at position 2 in the queue!"
- ✅ Notification body accurately displays: "You're up next! There is one user ahead of you. Please return to the app."
- ✅ Notification icon is PrismaX logo
- ✅ Notification badge is PrismaX logo
- ✅ Text is clear and readable, no spelling errors
- ✅ Tone is urgent, reminding user their turn is coming

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-012: No Notification Sent When Activating at Position #1**

**Priority**: P1 🟠  
**Test Type**: Functional Testing  
**Estimated Time**: 5 minutes (based on QN-M-010)

**Preconditions**:
1. Completed QN-M-010, current position is #2
2. Waiting for previous user to finish control

**Test Steps**:
1. Wait for position to move from #2 to #1
2. Observe whether new browser notification is received
3. Observe page state changes

**Expected Results**:
- ✅ When position reaches #1 and status becomes "active", no browser notification sent
- ✅ Page displays green in-app message: "It's your turn! You now have 5 minutes to control the robot."
- ✅ Automatically switches to control panel
- ✅ Countdown begins (5 minutes)

**Rationale**: User has their turn and should be on the page, no additional notification needed

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

### **Test Module E: Prevent Duplicate Notifications**

---

#### **Case QN-M-013: Same Position Does Not Send Duplicate Notifications**

**Priority**: P0 🔴  
**Test Type**: State Management Testing  
**Estimated Time**: 10 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission granted
3. Logged in with test account
4. Queue has enough users

**Test Steps**:
1. Join queue and wait for position to reach #6
2. After receiving first notification, record notification count (should be 1)
3. Stay at position #6 for about 30 seconds (don't move forward)
4. Observe whether duplicate notification received
5. Continue waiting for position to move to #2
6. After receiving second notification, similarly stay at position and observe

**Expected Results**:
- ✅ Position #6 receives only 1 notification, does not send duplicates
- ✅ Position #2 receives only 1 notification, does not send duplicates
- ✅ Total of only 2 notifications received (position #6 once, position #2 once)

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-014: No Duplicate Notifications After Fast Track**

**Priority**: P1 🟠  
**Test Type**: State Management Testing  
**Estimated Time**: 10 minutes

**Preconditions**:
1. Using desktop browser
2. Using Amplifier Member account (supports Fast Track)
3. Browser notification permission granted
4. Queue has enough users (at least 6 people)

**Test Steps**:
1. Join queue, position at #10 or later
2. Wait for position to reach #6, receive first notification
3. Immediately click "Fast Track" button
4. Complete Fast Track payment process (if needed)
5. Observe position jump (e.g. from #6 to #2 or #1)
6. Observe whether new notification received

**Expected Results**:
- ✅ Position #6 receives one notification
- ✅ After Fast Track position jumps, but does not resend position #6 notification
- ✅ If jump to position #2, receive position #2 notification (if not sent before)
- ✅ If jump to position #1, no notification (because already activated)
- ✅ Notification flags properly managed, Fast Track does not trigger duplicate notifications

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

### **Test Module F: State Reset**

---

#### **Case QN-M-015: Reset Notification Flags After Leaving Queue**

**Priority**: P0 🔴  
**Test Type**: State Management Testing  
**Estimated Time**: 15 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission granted
3. Logged in with test account

**Test Steps**:
1. Join queue, wait for position to reach #6
2. Receive position #6 notification
3. Continue waiting to position #4 or #3
4. Click "Leave Queue" button to leave queue
5. Observe page displays "You have left the queue" message
6. Immediately click "Enter Live Control" again to rejoin queue
7. If reaching position #6 again, observe whether notification received

**Expected Results**:
- ✅ First time at position #6 receives notification
- ✅ Successfully leave queue
- ✅ After rejoining queue, if reaching position #6 again, can receive notification again
- ✅ Notification flags properly reset

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-016: Reset Notification Flags After Control Activation**

**Priority**: P0 🔴  
**Test Type**: State Management Testing  
**Estimated Time**: 20 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission granted
3. Logged in with test account

**Test Steps**:
1. Join queue, wait for position to reach #6
2. Receive position #6 notification
3. Continue waiting to position #2, receive second notification
4. Continue waiting to position #1 and activate control
5. Observe control interface starts
6. Control for 5 minutes or manually end control
7. After control ends, immediately rejoin queue
8. Wait to reach position #6 and #2 again, observe notifications

**Expected Results**:
- ✅ First queue round: position #6 receives notification, position #2 receives notification
- ✅ Successfully activate control
- ✅ Rejoin queue after control ends
- ✅ Second queue round: position #6 can receive notification again, position #2 can receive notification again
- ✅ Notification flags properly reset after control activation

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

### **Test Module G: Boundary Conditions**

---

#### **Case QN-M-017: Skip Position #6 (Directly from #7 to #5)**

**Priority**: P1 🟠  
**Test Type**: Boundary Condition Testing  
**Estimated Time**: 15 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission granted
3. Logged in with test account

**Test Steps**:
1. Join queue, position at #7
2. Wait for queue update
3. Observe position change (may skip from #7 to #5 due to multiple people leaving simultaneously)
4. Observe whether position #6 notification received

**Expected Results**:
- ✅ If position skips #6 (directly from #7 to #5), no position #6 notification received
- ✅ System does not send notifications for positions not experienced
- ✅ Queue functionality operates normally

**Note**: This scenario requires multiple people leaving queue simultaneously, may need coordinated testing

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-018: Skip Position #2 (Directly from #3 to #1)**

**Priority**: P1 🟠  
**Test Type**: Boundary Condition Testing  
**Estimated Time**: 15 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission granted
3. Logged in with test account
4. Already received position #6 notification

**Test Steps**:
1. Wait for position to reach #3
2. Wait for queue update (may skip directly to #1 due to position #2 user leaving)
3. Observe whether position #2 notification received

**Expected Results**:
- ✅ If position skips #2 (directly from #3 to #1), no position #2 notification received
- ✅ Directly activate control (position #1)
- ✅ System does not send notifications for positions not experienced

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-019: Browser Does Not Support Notification API**

**Priority**: P1 🟠  
**Test Type**: Compatibility Testing  
**Estimated Time**: 5 minutes

**Preconditions**:
1. Using browser that does not support notification API (e.g. very old browser)
2. Or use developer tools to disable notification API:
   ```javascript
   delete window.Notification;
   ```
3. Logged in with test account

**Test Steps**:
1. Select robot on TeleOp page
2. Click "Enter Live Control" to join queue
3. Observe whether page displays error

**Expected Results**:
- ✅ No notification permission prompt displayed
- ✅ Queue functionality operates normally (core features not affected)
- ✅ No error messages displayed
- ✅ User can normally queue and control robot

**Rationale**: Notification feature is enhancement, should not affect core queue functionality

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-020: Rapidly Join/Leave Queue Consecutively**

**Priority**: P2 🟡  
**Test Type**: Stress Testing  
**Estimated Time**: 5 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission granted
3. Logged in with test account

**Test Steps**:
1. Quickly click "Enter Live Control" to join queue
2. Immediately click "Leave Queue" to leave queue
3. Repeat steps 1-2, consecutively 5 times
4. Observe page state and browser console

**Expected Results**:
- ✅ Each join/leave operation succeeds
- ✅ No error messages displayed
- ✅ No JavaScript errors in browser console
- ✅ Notification permission prompt shows/hides normally
- ✅ State management correct, no memory leaks

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

### **Test Module H: Cross-Browser Compatibility**

---

#### **Case QN-M-021: Chrome Browser Complete Flow**

**Priority**: P0 🔴  
**Test Type**: Compatibility Testing  
**Estimated Time**: 20 minutes

**Preconditions**:
1. Chrome browser 120+ (Windows/macOS/Linux)
2. Logged in with test account
3. Browser notification permission is "default"

**Test Steps**:
1. Execute complete flow:
   - Join queue
   - Show permission prompt
   - Grant notification permission
   - Wait for position #6, receive notification
   - Wait for position #2, receive notification
   - Leave queue
   - Rejoin queue and verify notification reset

**Expected Results**:
- ✅ All features work normally on Chrome
- ✅ Notifications display elegantly, following Chrome notification style
- ✅ Performance smooth, no lag
- ✅ No console errors

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-022: Firefox Browser Complete Flow**

**Priority**: P1 🟠  
**Test Type**: Compatibility Testing  
**Estimated Time**: 20 minutes

**Preconditions**:
1. Firefox browser 120+ (Windows/macOS/Linux)
2. Logged in with test account
3. Browser notification permission is "default"

**Test Steps**:
1. Execute same complete flow as QN-M-021

**Expected Results**:
- ✅ All features work normally on Firefox
- ✅ Notifications display elegantly, following Firefox notification style
- ✅ Permission request process follows Firefox standards
- ✅ No console errors

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-023: Safari Browser Complete Flow**

**Priority**: P1 🟠  
**Test Type**: Compatibility Testing  
**Estimated Time**: 20 minutes

**Preconditions**:
1. Safari browser 17+ (macOS)
2. Logged in with test account
3. Browser notification permission is "default"

**Test Steps**:
1. Execute same complete flow as QN-M-021
2. Pay special attention to Safari's notification permission management

**Expected Results**:
- ✅ All features work normally on Safari
- ✅ Notifications display elegantly, following macOS notification center style
- ✅ Safari's special permission request process works normally
- ✅ No console errors

**Note**: Safari has late support for notification API, needs special verification

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-024: iOS Safari Mobile Verification**

**Priority**: P1 🟠  
**Test Type**: Compatibility Testing  
**Estimated Time**: 10 minutes

**Preconditions**:
1. iOS 17+ device, using Safari browser
2. Logged in with test account

**Test Steps**:
1. Open PrismaX TeleOp page in iOS Safari
2. Join queue
3. Observe whether permission prompt displayed

**Expected Results**:
- ✅ No notification permission prompt displayed (mobile)
- ✅ Queue functionality operates normally
- ✅ UI adapted for mobile
- ✅ No functional issues

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-025: Android Chrome Mobile Verification**

**Priority**: P1 🟠  
**Test Type**: Compatibility Testing  
**Estimated Time**: 10 minutes

**Preconditions**:
1. Android 13+ device, using Chrome browser
2. Logged in with test account

**Test Steps**:
1. Open PrismaX TeleOp page in Android Chrome
2. Join queue
3. Observe whether permission prompt displayed

**Expected Results**:
- ✅ No notification permission prompt displayed (mobile)
- ✅ Queue functionality operates normally
- ✅ UI adapted for mobile
- ✅ No functional issues

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

### **Test Module I: User Experience & Performance**

---

#### **Case QN-M-026: Notification Response Time Verification**

**Priority**: P2 🟡  
**Test Type**: Performance Testing  
**Estimated Time**: 15 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission granted
3. Open browser developer tools (Network and Performance tabs)

**Test Steps**:
1. Join queue and wait for position to reach #6
2. Record timestamp of queue position update (via Socket.IO event)
3. Record timestamp of browser notification display
4. Calculate latency

**Expected Results**:
- ✅ Latency from queue position update to notification display < 500ms
- ✅ User feels notification is instant
- ✅ No noticeable lag or delay

**Actual Results**:  
Latency: _________ ms

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-027: Permission Prompt UI Verification**

**Priority**: P2 🟡  
**Test Type**: UI/UX Testing  
**Estimated Time**: 5 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission is "default"
3. Using standard viewport: 1280x720

**Test Steps**:
1. Join queue, show permission prompt
2. Carefully check visual effects of prompt
3. Compare with PrismaX design standards

**Expected Results**:
- ✅ Prompt background color: #1a2332 (dark)
- ✅ Border color: #2a3647
- ✅ Border radius: 12px
- ✅ Enable button color: #38CB89 (green)
- ✅ Mouse hover on Enable button changes color to #059669
- ✅ Close button (X) in top right corner, gray, turns white on hover
- ✅ Text clear and readable, reasonable spacing
- ✅ Overall elegant, follows PrismaX brand style

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-028: Notification Click Behavior Verification**

**Priority**: P2 🟡  
**Test Type**: Functional Testing  
**Estimated Time**: 10 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission granted
3. PrismaX tab in background

**Test Steps**:
1. Join queue
2. Switch to other tab or minimize browser
3. Wait for position to reach #6, receive notification
4. Click browser notification

**Expected Results**:
- ✅ After clicking notification, browser window is focused
- ✅ PrismaX tab is activated and displayed in foreground
- ✅ User can immediately see queue status
- ✅ Improves user convenience to return to app

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

#### **Case QN-M-029: Notification Auto-Close Time Verification**

**Priority**: P2 🟡  
**Test Type**: Functional Testing  
**Estimated Time**: 15 minutes

**Preconditions**:
1. Using desktop browser
2. Browser notification permission granted
3. Prepare timer

**Test Steps**:
1. Join queue and wait for position to reach #6
2. Start timer immediately after receiving notification
3. Do not click or close notification
4. Wait for notification to auto-dismiss
5. Record notification display duration

**Expected Results**:
- ✅ Notification auto-closes after about 12 seconds
- ✅ Allow margin of error: ±1 second (i.e. 11-13 seconds)
- ✅ Notification does not stay indefinitely

**Actual Results**:  
Actual display duration: _________ seconds

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

### **Test Module J: Regression Testing**

---

#### **Case QN-M-030: Core Queue Functionality Not Affected**

**Priority**: P0 🔴  
**Test Type**: Regression Testing  
**Estimated Time**: 15 minutes

**Preconditions**:
1. Using desktop browser
2. Logged in with test account

**Test Steps**:
1. Test complete queue flow (regardless of notification permission status):
   - Join queue
   - View queue list (shows all queued users)
   - View own position and countdown
   - Wait for own turn (position #1, status active)
   - Activate control
   - Control robot for 5 minutes
   - Control ends
   - Leave queue

**Expected Results**:
- ✅ All core queue features work normally
- ✅ Notification feature is enhancement, does not affect core logic
- ✅ Regardless of notification permission status, queue operates normally
- ✅ User can normally control robot

**Actual Results**:  
_[Fill in during testing]_

**Test Status**: ⬜ Pass / ⬜ Fail / ⬜ Blocked  
**Defect ID**: _[If any]_  
**Test Date**: ___________  
**Tester**: ___________

---

## 📊 Test Execution Record

### Test Summary

| Test Module | Case Count | P0 Cases | P1 Cases | P2 Cases | Pass | Fail | Blocked |
|------------|------------|----------|----------|----------|------|------|---------|
| A. Notification Permission Request - Desktop | 6 | 3 | 3 | 0 | | | |
| B. Notification Permission Request - Mobile | 1 | 1 | 0 | 0 | | | |
| C. Notification Trigger - Position #6 | 2 | 1 | 1 | 0 | | | |
| D. Notification Trigger - Position #2 | 3 | 1 | 2 | 0 | | | |
| E. Prevent Duplicate Notifications | 2 | 1 | 1 | 0 | | | |
| F. State Reset | 2 | 2 | 0 | 0 | | | |
| G. Boundary Conditions | 4 | 0 | 3 | 1 | | | |
| H. Cross-Browser Compatibility | 5 | 1 | 4 | 0 | | | |
| I. User Experience & Performance | 4 | 0 | 0 | 4 | | | |
| J. Regression Testing | 1 | 1 | 0 | 0 | | | |
| **Total** | **30** | **11** | **14** | **5** | | | |

### Priority Levels
- **P0 (Blocker)** 🔴: Core functionality, must pass before release
- **P1 (Critical)** 🟠: Important functionality, strongly recommended to fix
- **P2 (Major)** 🟡: Enhancement functionality, can be optimized later

---

## 🐛 Defect Report Template

**Defect Title**: [PRIS-84] [Module Name] Brief Description

**Priority**: P0 / P1 / P2  
**Severity**: Blocker / Critical / Major / Minor  
**Test Case ID**: QN-M-XXX

**Environment Info**:
- Browser: Chrome 120.0.6099.109
- Operating System: Windows 11 / macOS 14.2
- Test Environment: QA / Staging
- Account Type: Amplifier Member
- Robot: arm1

**Reproduction Steps**:
1. 
2. 
3. 

**Expected Result**:

**Actual Result**:

**Screenshots/Video**:
[Attachments]

**Console Errors**:
```
[Paste error logs]
```

**Additional Info**:

---

## 📈 Test Completion Criteria

### Release Entry Criteria
- ✅ All P0 cases 100% passed
- ✅ P1 case pass rate ≥ 95%
- ✅ P2 case pass rate ≥ 90%
- ✅ No unresolved P0/P1 level defects
- ✅ Chrome browser 100% compatible
- ✅ Core queue functionality not affected (regression testing passed)

### Recommended Pre-Release Checklist
- [ ] All test cases executed
- [ ] Test report generated
- [ ] All Critical defects fixed and verified
- [ ] Cross-browser testing completed
- [ ] Performance metrics meet expectations
- [ ] Product manager reviewed test results
- [ ] Development team confirmed code quality

---

## 🔧 Testing Tips & Notes

### Permission Management Tips
1. **Reset browser notification permission**:
   - Chrome: Settings → Privacy and security → Site Settings → Notifications → Find prismax.ai → Remove
   - Firefox: Settings → Privacy & Security → Permissions → Notifications → Settings → Remove website
   - Safari: Preferences → Websites → Notifications → Remove prismax.ai

2. **Quickly test different permission states**:
   - Use browser incognito mode (always default state)
   - Use multiple browser profiles

### Queue Testing Tips
1. **Quickly reach test position**:
   - Use multiple test accounts to join queue simultaneously
   - Coordinate with other testers to quickly leave queue
   - In test environment, can request dev to adjust queue parameters

2. **Monitor Socket.IO events**:
   - Open browser console
   - Observe `queue_update` events
   - Verify position change accuracy

3. **Verify notifications**:
   - Use screen recording tool to record entire test process
   - Screenshot save each notification content
   - Use timer to precisely measure time

### Common Issue Troubleshooting
1. **Notification not displaying**:
   - Check browser permission status
   - Check system notification settings (Windows/macOS)
   - Check browser console for errors
   - Confirm queue position actually reached trigger point

2. **Permission prompt not displaying**:
   - Confirm desktop (width > 1000px)
   - Confirm permission status is "default"
   - Check browser console errors

3. **Receiving duplicate notifications**:
   - This is a defect, needs to be reported
   - Record detailed reproduction steps
   - Check if Fast Track or rejoined queue

---

## 📚 References

- **Code Files**:
  - `src/components/TeleOp/TeleOpQueueBody.js` (lines 230-234, 263-264)
  - `src/components/TeleOp/TeleOpRightPanel.js` (lines 182-194, 227-228, 464-479)
  - `src/components/TeleOp/QueuePanel.module.css` (lines 389-446)

- **Related Documentation**:
  - [Notification API - MDN](https://developer.mozilla.org/en-US/docs/Web/API/Notifications_API)
  - [Browser Notification Permissions](https://developer.mozilla.org/en-US/docs/Web/API/Notification/permission)
  - PRIS-84 Jira Ticket

- **Git Commits**:
  - `a7588c2` - Add browser queue notifications
  - `faecce5` - Reset notification flags and optimize mobile experience
  - `72c5a34` - Merge PR #12

---

## ✅ Review Record

| Date | Reviewer | Role | Status | Notes |
|------|----------|------|--------|-------|
| 2026-01-21 | ___________ | QA Lead | ⬜ Pending Review | |
| | ___________ | Dev Lead | ⬜ Pending Review | |
| | ___________ | Product Manager | ⬜ Pending Review | |

---

**Document Version**: v1.0  
**Created Date**: 2026-01-21  
**Last Updated**: 2026-01-21  
**Document Owner**: QA Team  
**Next Review Date**: 2026-02-21

---

## 📝 Test Execution Signature

**Test Executor**: ___________________  
**Execution Date**: ___________________  
**Test Environment**: ___________________  
**Test Result**: PASS / FAIL / PARTIAL  

**Notes**:  
_________________________________________________________________  
_________________________________________________________________  
_________________________________________________________________
