## 含有 chain 字段的 API 列表（app_prismax_user_management）

本文档整理了后端 `app_prismax_user_management` 中所有涉及 `chain` 字段的 API 列表，并补充了每个接口的请求示例。

- 默认链：`chain` 未提供时默认 `solana`
- 可选链：`solana`、`ethereum`、`base`（大小写不敏感，服务端会转为小写）
- 说明中的 HOST 以本地举例：`http://localhost:8080`，请按实际部署地址替换

---

### 1) POST `/auth/twitter/initiate`
- 含 `chain`（请求体，可选，默认 `solana`）
- 需认证：`Authorization: Bearer <TOKEN>` 或在 body 中提供 `token`
- 其他主要字段：`email?`、`wallet_address?`、`return_url?`

请求示例（通过钱包地址发起，链为 solana）

```bash
curl -X POST 'http://localhost:8080/auth/twitter/initiate' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -d '{
    "wallet_address": "So1anaWalletAddressHere",
    "chain": "solana",
    "return_url": "https://app.example.com/twitter/callback"
  }'
```

- 前端入口
  - `app-prismax-rp/src/components/Account/Account.js`：发起 Twitter 绑定与授权流程
  - 触发与UI路径：账户页 → Personal info → Twitter → “Link Twitter” 按钮
  - 代码片段（Account.js，handleTwitterLink 完整上下文）

```454:552:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/src/components/Account/Account.js
    const handleTwitterLink = useCallback(async () => {
        const token = localStorage.getItem('gatewayToken');
        if (!token) {
            showNotification('error', 'Authentication token missing. Please log in again.');
            return;
        }

        const storedEmail = localStorage.getItem('userEmail') || '';
        const storedWalletAddress = localStorage.getItem('walletAddress') || '';

        if (!storedEmail && !storedWalletAddress) {
            showNotification('error', 'No account information found. Please sign in again.');
            return;
        }

        const returnUrl = `${window.location.origin}/account`;

        const requestBody = {
            chain: (selectedChain || 'solana'),
            return_url: returnUrl
        };

        if (storedEmail) {
            requestBody.email = storedEmail.toLowerCase();
        } else {
            requestBody.wallet_address = storedWalletAddress;
        }

        const preferPopup = !isMobileDevice();
        let popupWindow = null;
        let popupReady = false;

        const preparePopupWindow = () => {
            const newWindow = window.open('about:blank', '_blank');
            if (!newWindow) {
                return null;
            }

            try {
                newWindow.opener = null;
                newWindow.document.write(
                    '<!DOCTYPE html><html><head><title>Prismax</title></head>' +
                    '<body style="background:#030712;color:#FFFFFF;font-family:Arial,Helvetica,sans-serif;' +
                    'display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">' +
                    '<p>Redirecting to Twitter...</p>' +
                    '</body></html>'
                );
                newWindow.document.close();
            } catch (popupError) {
                console.warn('Unable to prepare Twitter popup window.', popupError);
            }

            return newWindow;
        };

        if (preferPopup) {
            popupWindow = preparePopupWindow();
            popupReady = Boolean(popupWindow);
        }

        try {
            setIsLinkingTwitter(true);
            const response = await fetch(`${PRISMAX_BACKEND_URL}/auth/twitter/initiate`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });

            const result = await response.json().catch(() => ({}));

            if (response.ok && result.success && result.authorization_url) {
                if (popupReady && popupWindow) {
                    popupWindow.location.href = result.authorization_url;
                    popupWindow.focus();
                } else {
                    window.location.href = result.authorization_url;
                }
                return;
            }

            if (popupWindow && !popupWindow.closed) {
                popupWindow.close();
            }

            const errorMsg = result?.msg || 'Unable to start Twitter verification. Please try again.';
            showNotification('error', errorMsg);
        } catch (err) {
            if (popupWindow && !popupWindow.closed) {
                popupWindow.close();
            }
            console.error('Error initiating Twitter OAuth:', err);
            showNotification('error', 'Unable to start Twitter verification. Please try again.');
        } finally {
            setIsLinkingTwitter(false);
        }
    }, [selectedChain, showNotification]);
```

---

### 2) GET `/api/get-users`
- 含 `chain`（查询参数，可选，默认 `solana`）
- 通过 `wallet_address` 查询时可不带 token；通过 `email` 查询需要 `Authorization` 或 `token`
- 其他常见参数：
  - `email?`、`wallet_address?`
  - `token?`（可放 Header 的 Bearer 或 query/body 中）
  - `recaptcha_token`（非测试环境必填）
  - `referrers_referral_code?`

请求示例（按钱包地址查询，以 Ethereum 为例）

```bash
curl -G 'http://localhost:8080/api/get-users' \
  --data-urlencode 'wallet_address=0xYourEthereumAddress' \
  --data-urlencode 'chain=ethereum' \
  --data-urlencode 'recaptcha_token=RECAPTCHA_TOKEN_VALUE'
```

请求示例（按邮箱查询，需携带认证）

```bash
curl -G 'http://localhost:8080/api/get-users' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  --data-urlencode 'email=user@example.com' \
  --data-urlencode 'chain=solana' \
  --data-urlencode 'recaptcha_token=RECAPTCHA_TOKEN_VALUE'
```

- 前端入口
  - `app-prismax-rp/src/context/SwapMainAppContext.js`：应用启动/上下文拉取用户信息
  - `app-prismax-rp/src/components/header/ConnectWalletHeader.js`：连接钱包后拉取用户信息
  - `app-prismax-rp/src/components/Account/Account.js`：账户页数据加载
  - `app-prismax-rp/src/components/Admin/UserTable.js`：管理后台用户列表
  - 触发与UI路径：
    - 进入应用后（上下文初始化）自动请求；连接钱包/登录成功后自动请求
    - 进入账户页自动请求；管理后台用户表页面加载自动请求
  - 代码片段（Account.js，fetchUserInfo 完整上下文）

```113:166:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/src/components/Account/Account.js
    const fetchUserInfo = useCallback(async () => {
        // Use this variable to handle the fallback case in the finally block
        let fetchSuccess = false;
        // Get user identifiers and token
        const userEmail = localStorage.getItem('userEmail') || '';
        const walletAddress = localStorage.getItem('walletAddress');
        const token = localStorage.getItem('gatewayToken');
        const emailLoginFlag = localStorage.getItem('emailLogin') === 'true';
        
        try {
            setIsLoading(true);

            if (!userEmail && !walletAddress) {
                setIsLoading(false);
                return;
            }

            setIsEmailLogin(emailLoginFlag);

            if (!token) {
                console.error('No authentication token found');
                setIsLoading(false);
                return;
            }

            // Generate a reCAPTCHA token to include in fetch request
            if (!isRecaptchaReady) {
                console.error('reCAPTCHA is not ready to fetch user info. Defaulting to fallback user info.');
                return;
            }
            const recaptchaToken = await executeRecaptchaAction('fetch_user_info');

            // Build query params
            const params = new URLSearchParams();
            if (userEmail) {
                params.append('email', userEmail);
            } else if (walletAddress) {
                params.append('wallet_address', walletAddress);
            }
            params.append('chain', selectedChain || 'solana');
            params.append('recaptcha_token', recaptchaToken);

            // Fetch user info from backend
            const response = await fetch(`${PRISMAX_BACKEND_URL}/api/get-users?${params}`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });
```

```196:241:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/src/context/SwapMainAppContext.js
    const fetchUserInfoAfterConnect = async () => {
        try {
            // Wait for reCAPTCHA to be ready before making the request
            if (!isRecaptchaReady) {
                console.log('Waiting for reCAPTCHA to be ready before fetching user info');
                return;
            }

            // Generate reCAPTCHA token
            const recaptchaToken = await executeRecaptchaAction('fetch_user_info');

            let url = `${PRISMAX_BACKEND_URL}/api/get-users`;
            let headers = {
                'Content-Type': 'application/json'
            };

            if (userEmail) {
                if (!gatewayToken) {
                    console.error('No token found for email authentication');
                    return;
                }

                const params = new URLSearchParams();
                params.append('email', userEmail);
                params.append('chain', selectedChain);
                params.append('recaptcha_token', recaptchaToken);
                url += `?${params}`;

                headers['Authorization'] = `Bearer ${gatewayToken}`;
                // todo could be issue here
                // } else if (walletAddress) {
                //     const params = new URLSearchParams();
                //     params.append('wallet_address', walletAddress);
                //     url += `?${params}`;
                // }
            } else {
                console.error('No email  available');
                return;
            }

            const response = await fetch(url, {
                method: 'GET',
                headers: headers
            });
```

```15:38:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/src/components/Admin/UserTable.js
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const response = await fetch(`${PRISMAX_BACKEND_URL}/api/get-users`);
        if (!response.ok) {
          throw new Error('Failed to fetch users');
        }
        const data = await response.json();
        if (data.success && data.data) {
          setUsers(data.data);
          console.log("!!!data", data.data)
          setTotalPages(Math.ceil(data.data.length / itemsPerPage));
        } else {
          throw new Error('Invalid data format');
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchUsers();
  }, []);
```

---

### 3) POST `/api/disconnect-wallet-from-email`
- 含 `chain`（请求体，可选，默认 `solana`）
- 必填：`email`、`wallet_address`
- 需认证：`Authorization: Bearer <TOKEN>` 或在 body 中提供 `token`

请求示例（解绑邮箱与钱包，链为 base）

```bash
curl -X POST 'http://localhost:8080/api/disconnect-wallet-from-email' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -d '{
    "email": "user@example.com",
    "wallet_address": "0xBaseWalletAddressHere",
    "chain": "base"
  }'
```

- 前端入口
  - `app-prismax-rp/src/components/Account/Account.js`：解绑邮箱与钱包
  - 触发与UI路径：账户页 → 钱包区域 → “Unlink Wallet” 图标点击
  - 代码片段（Account.js，handleDisconnectWallet 完整上下文）

```585:631:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/src/components/Account/Account.js
    const handleDisconnectWallet = async () => {
        try {
            const token = localStorage.getItem('gatewayToken');
            if (!token) {
                console.error('No authentication token found');
                return;
            }

            const userEmail = localStorage.getItem('userEmail');
            const walletAddress = localStorage.getItem('walletAddress');
            const chain = selectedChain || 'solana';

            const response = await fetch(`${PRISMAX_BACKEND_URL}/api/disconnect-wallet-from-email`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    email: userEmail,
                    wallet_address: walletAddress,
                    chain
                })
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    // Remove wallet info from local storage and context and reload the page
                    disconnect();
                    localStorage.removeItem('walletAddress');
                    localStorage.removeItem('lastConnectedWallet');
                    localStorage.removeItem('lastConnectedChain');
                    localStorage.removeItem('selectedChain');
                    // Set walletDisconnectSuccess to trigger a notification on page reload
                    localStorage.setItem('walletDisconnectSuccess', true);
                    window.location.reload();
                } else {
                    console.error('Error disconnecting the wallet:', result?.msg)
                    showNotification('error', 'Failed to unlink your wallet. Please try again.')
                }
            }
        } catch (error) {
            console.error('Error disconnecting the wallet:', error);
            showNotification('error', 'Failed to unlink your wallet. Please try again.')
        }
    };
```

---

### 4) POST `/api/update-user-info`
- 含 `chain`（请求体，可选，默认 `solana`）
- 需提供 `email` 或 `wallet_address` 之一用于定位用户
- 需认证：`Authorization: Bearer <TOKEN>` 或在 body 中提供 `token`
- 可更新字段：`user_name`、`user_profile_email?`、`telegram_id?`、`twitter_name?`/`user_profile_twitter_name?`、`phone_number?` 等

请求示例（通过钱包地址更新用户名，链为 ethereum）

```bash
curl -X POST 'http://localhost:8080/api/update-user-info' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -d '{
    "wallet_address": "0xYourEthereumAddress",
    "chain": "ethereum",
    "user_name": "Alice"
  }'
```

- 前端入口
  - `app-prismax-rp/src/components/Account/Account.js`：更新用户资料（用户名、社媒、电话等）
  - 触发与UI路径：账户页 → Personal info → “Edit” → 修改 → “Save”
  - 代码片段（Account.js，saveUserInfo 完整上下文）

```314:367:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/src/components/Account/Account.js
    const saveUserInfo = useCallback(async (overrideValues = {}) => {
        const storedEmail = localStorage.getItem('userEmail') || '';
        const storedWalletAddress = localStorage.getItem('walletAddress') || '';
        const token = localStorage.getItem('gatewayToken');

        if (!token) {
            console.error('No authentication token found');
            showNotification('error', 'Authentication token missing. Please log in again.');
            return false;
        }

        const nextInfo = {
            ...editedInfo,
            ...overrideValues
        };

        const sanitizedInfo = {
            userName: nextInfo.userName?.trim() || '',
            email: nextInfo.email?.trim() || '',
            telegramId: nextInfo.telegramId?.trim() || '',
            twitterId: nextInfo.twitterId?.trim() || '',
            twitterName: nextInfo.twitterName?.trim() || '',
            phoneNumber: nextInfo.phoneNumber?.trim() || ''
        };

        const payload = {
            ...(storedEmail ? {email: storedEmail} : {wallet_address: storedWalletAddress}),
            user_name: sanitizedInfo.userName,
            telegram_id: sanitizedInfo.telegramId,
            phone_number: sanitizedInfo.phoneNumber,
            chain: (selectedChain || 'solana')
        };

        if (Object.prototype.hasOwnProperty.call(overrideValues, 'twitterId')) {
            payload.twitter_id = sanitizedInfo.twitterId;
        }

        if (Object.prototype.hasOwnProperty.call(overrideValues, 'twitterName')) {
            payload.twitter_name = sanitizedInfo.twitterName;
        }

        if (sanitizedInfo.email) {
            payload.user_profile_email = sanitizedInfo.email.toLowerCase();
        }

        try {
            const response = await fetch(`${PRISMAX_BACKEND_URL}/api/update-user-info`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
```

---

### 5) POST `/api/daily-login-points`
- 含 `chain`（请求体，可选，默认 `solana`）
- 需提供 `wallet_address` 或 `email`
- 可选：`user_local_date`（格式 `YYYY-MM-DD`；未提供时由服务端按 UTC±1 天规则校验）

请求示例（使用邮箱，链为 solana）

```bash
curl -X POST 'http://localhost:8080/api/daily-login-points' \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "user@example.com",
    "chain": "solana",
    "user_local_date": "2025-11-18"
  }'
```

- 前端入口
  - `app-prismax-rp/src/context/SwapMainAppContext.js`：每日登录积分打点
  - 触发与UI路径：应用上下文初始化或登录/连接钱包后自动触发（无按钮）
  - 代码片段（SwapMainAppContext.js，handleDailyLoginPoints 完整上下文）

```273:301:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/src/context/SwapMainAppContext.js
    const handleDailyLoginPoints = async () => {
        try {
            const requestBody = {};
            if (userEmail) {
                requestBody.email = userEmail;
            } else if (walletAddress) {
                requestBody.wallet_address = walletAddress;
                requestBody.chain = selectedChain;
            } else {
                return;
            }
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');

            requestBody.user_local_date = `${year}-${month}-${day}`;
            const response = await fetch(`${PRISMAX_BACKEND_URL}/api/daily-login-points`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data.is_first_time) {
                    setShowFirstTimeModal(true);
                    setPointsRefreshTrigger(prev => prev + 1);
                } else if (data.success && data.data.points_awarded_today > 0) {
                    showNotification('success', `Welcome! You earned ${data.data.points_awarded_today} points today!`);
                    setPointsRefreshTrigger(prev => prev + 1);
                }
            }
        } catch (error) {
            console.error('Error handling daily login points:', error);
        }
    };
```

---

### 6) GET `/api/get-point-transactions`
- 含 `chain`（查询参数，可选，默认 `solana`）
- 需提供 `wallet_address` 或 `email` 之一

请求示例（按邮箱查询 Base 链积分流水）

```bash
curl -G 'http://localhost:8080/api/get-point-transactions' \
  --data-urlencode 'email=user@example.com' \
  --data-urlencode 'chain=base'
```

请求示例（按钱包地址查询 Solana 链积分流水）

```bash
curl -G 'http://localhost:8080/api/get-point-transactions' \
  --data-urlencode 'wallet_address=So1anaWalletAddressHere' \
  --data-urlencode 'chain=solana'
```

- 前端入口
  - `app-prismax-rp/src/components/Dashboard/Dashboard.js`：查询并展示积分流水
  - 触发与UI路径：打开 Dashboard 页面时自动拉取；分页/刷新时再次拉取
  - 代码片段（Dashboard.js，fetchPointsData 完整上下文）

```104:164:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/src/components/Dashboard/Dashboard.js
    const fetchPointsData = async () => {
        try {
            const params = new URLSearchParams();
            if (userEmail) {
                params.append('email', userEmail);
            } else if (walletAddress) {
                params.append('wallet_address', walletAddress);
            }
            params.append('chain', selectedChain || 'solana');

            const queryParam = params.toString() ? `?${params.toString()}` : '';
            const transResponse = await fetch(`${PRISMAX_BACKEND_URL}/api/get-point-transactions${queryParam}`);

            if (transResponse.ok) {
                const transData = await transResponse.json();
                if (transData.success && transData.data) {
                    if (typeof transData.total_points !== 'undefined') {
                        const points = Math.floor(transData.total_points || 0);
                        setOverallPoints(points.toLocaleString());
                    }
                    const today = new Date();
                    today.setHours(0, 0, 0, 0);
                    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

                    const todayTransactions = transData.data.filter(trans => {
                        // Use user_local_date if available, otherwise convert UTC to local time
                        let transDate;
                        let transDateStr
                        if (trans.user_local_date) {
                            transDate = new Date(trans.user_local_date);
                            transDateStr = transDate.toISOString().split('T')[0];

                        } else if (trans.created_at_utc) {
                            // Convert UTC to local time
                            transDate = new Date(trans.created_at_utc);
                            // Get the date string in local timezone
                            const year = transDate.getFullYear();
                            const month = String(transDate.getMonth() + 1).padStart(2, '0');
                            const dayNum = String(transDate.getDate()).padStart(2, '0');
                            transDateStr = `${year}-${month}-${dayNum}`;
                        } else {

                            return false;
                        }


                        return transDateStr === todayStr && trans.points_change > 0;
                    });

                    const todayTotal = todayTransactions.reduce((sum, trans) => sum + trans.points_change, 0);
                    setTodayPoints(Math.floor(todayTotal));

                    prepareChartData(transData.data);
                }
            }
        } catch (error) {
            console.error('Error fetching points data:', error);
        } finally {
            setLoading(false);
        }
    };
```

---

### 7) POST `/api/record-crypto-payment`
- 含 `chain`（请求体，可选，默认 `solana`）
- 必填：`wallet_address`、`amount_total`、`user_id`
- 可选：`transaction_hash`（或兼容旧字段 `solana_transaction_hash`）、`currency`（如 `USDT`/`USD` 等）
- 说明：成功时响应 `data` 中会包含 `payment_chain` 和（回显的）`chain`

请求示例（记录一笔 ETH/Base 生态支付，这里以 Base 为例）

```bash
curl -X POST 'http://localhost:8080/api/record-crypto-payment' \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": 12345,
    "wallet_address": "0xBaseWalletAddressHere",
    "amount_total": 99,
    "currency": "USDT",
    "transaction_hash": "0xTxHashHere",
    "chain": "base"
  }'
```

- 前端入口
  - `app-prismax-rp/src/components/header/ConnectWalletHeader.js`：购买/升级时记录链上支付
  - 触发与UI路径：在头部连接钱包并完成链上支付交易后自动上报（无按钮直接对应）
  - 代码片段（ConnectWalletHeader.js，transferSplToken 内部上报）

```1510:1629:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/src/components/header/ConnectWalletHeader.js
    const transferSplToken = async (fromPublicKeyStr, provider, tokenType, C2C_RECEIVING_TOKEN_ACCOUNT) => {
        try {
            const connection = new Connection(RPC_URL, "confirmed");
            const fromPublicKey = new PublicKey(fromPublicKeyStr);
            let tokenMintAddress;
            let toTokenAccountPubkey;
            let readableToken;
            if (tokenType === 'USDT') {
                tokenMintAddress = usdtTokenAddress;
                readableToken = "USDT";
                const toTokenAddress = await getTokenAccountFromWalletAddress(prismaxRecevingAddress, usdtTokenAddress)
                toTokenAccountPubkey = new PublicKey(toTokenAddress);
            } else if (tokenType === 'USDC') {
                tokenMintAddress = usdcTokenAddress;
                readableToken = "USDC";
                const toTokenAddress = await getTokenAccountFromWalletAddress(prismaxRecevingAddress, usdcTokenAddress)
                toTokenAccountPubkey = new PublicKey(toTokenAddress);
            } else {
                showNotification('error', "Unknown token type. Canceling transaction.");
                return;
            }

            const latestBlockhash = await connection.getLatestBlockhash("confirmed");
            let signature;

            // prepare a signer object
            const payer = {
                publicKey: fromPublicKey,
                signTransaction: async (transaction) => {
                    return await provider.signTransaction(transaction);
                },
            };

            const mintPubkey = new PublicKey(tokenMintAddress);
            const fromTokenAccount = await getOrCreateAssociatedTokenAccount(
                connection,
                payer,
                mintPubkey,
                fromPublicKey
            );
            const amountInBaseUnits = Math.floor(Number(amount) * 1_000_000);
            if (isNaN(amountInBaseUnits) || amountInBaseUnits <= 0) {
                showNotification('error', `Invalid ${readableToken} amount. Please provide a positive number.`);
                return;
            }
            // Create the transfer instruction
            const transferIx = createTransferInstruction(
                fromTokenAccount.address,
                toTokenAccountPubkey,
                fromPublicKey,
                amountInBaseUnits
            );

            const memoText = `Send ${amount} ${readableToken} to ${toTokenAccountPubkey.toBase58()}`;
            const memoIx = new TransactionInstruction({
                keys: [],
                programId: new PublicKey('MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr'),
                data: Buffer.from(memoText, 'utf8'),
            });

            // Build the transaction with transfer + memo
            const transaction = new Transaction().add(transferIx).add(memoIx);
            transaction.feePayer = fromPublicKey;
            transaction.recentBlockhash = latestBlockhash.blockhash;

            const result = await provider.signAndSendTransaction(transaction);
            signature = result.signature;
            console.log("signature", signature);

            const explorerLink = `https://solscan.io/tx/${signature}`;
            showNotification('success', `Transfer of ${amount} ${readableToken} successfully submitted.
                 <a href="${explorerLink}" target="_blank" rel="noreferrer">Check on Explorer</a>`);

            await new Promise(resolve => setTimeout(resolve, 3000));
            await fetchBalancesAndNotifyParent(provider, fromPublicKeyStr, onWalletConnected, showNotification, selectedChain);
            try {

                const requestBody = {
                    wallet_address: fromPublicKeyStr,
                    amount_total: amount,
                    user_id: localStorage.getItem('userId'),
                    solana_transaction_hash: signature,
                    currency: selectedToken,
                    chain: selectedChain || 'solana'
                };

                const response = await fetch(`${PRISMAX_BACKEND_URL}/api/record-crypto-payment`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(requestBody)
                });
                const data = await response.json();
                if (data.success) {
                    onMembershipPaymentSuccess(data.solana_transaction_hash);

                }
                if (!response.ok) {
                    throw new Error(`Server responded with status ${response.status}`);
                }
```

---

### 通用说明与注意事项
- `chain` 默认值为 `solana`，仅接受：`solana`、`ethereum`、`base`
- 某些接口（如 `/api/get-users`）在使用邮箱查询时需要认证：`Authorization: Bearer <TOKEN>` 或通过参数 `token` 提供
- `/api/get-users` 在非测试环境需要 `recaptcha_token`
- 钱包相关查询会根据 `chain` 动态选择不同的地址列（如 `solana_receive_address` / `ethereum_receive_address` / `base_receive_address`）


