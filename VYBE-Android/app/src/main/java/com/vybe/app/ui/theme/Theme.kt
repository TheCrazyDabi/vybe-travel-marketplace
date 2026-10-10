package com.vybe.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val VybeLightColors = lightColorScheme(
    primary = Coral,
    onPrimary = Ocean, // verified contrast on web: 5.51:1
    primaryContainer = Sand,
    onPrimaryContainer = Ocean,
    secondary = Ocean,
    onSecondary = SurfaceWhite,
    background = OffWhite,
    onBackground = Ocean,
    surface = SurfaceWhite,
    onSurface = Ocean,
    surfaceVariant = Sand,
    onSurfaceVariant = Ocean,
    outline = BorderSand,
    error = DangerRed,
    tertiary = SuccessGreen
)

private val VybeDarkColors = darkColorScheme(
    primary = Coral,
    onPrimary = Ocean,
    background = Ocean,
    onBackground = SurfaceWhite,
    surface = Ocean,
    onSurface = SurfaceWhite
)

@Composable
fun VybeTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = if (darkTheme) VybeDarkColors else VybeLightColors,
        typography = VybeTypography,
        content = content
    )
}
