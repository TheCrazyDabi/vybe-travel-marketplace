package com.vybe.app.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// Clean hierarchy mirroring the web app (headline / section / body / muted).
val VybeTypography = Typography(
    headlineLarge = Typography().headlineLarge.copy(fontWeight = FontWeight.Black),
    headlineSmall = Typography().headlineSmall.copy(fontWeight = FontWeight.Bold),
    titleMedium = Typography().titleMedium.copy(fontWeight = FontWeight.Bold),
    bodyLarge = Typography().bodyLarge.copy(lineHeight = 24.sp),
    bodyMedium = Typography().bodyMedium,
    labelSmall = Typography().labelSmall.copy(letterSpacing = 1.5.sp)
)
