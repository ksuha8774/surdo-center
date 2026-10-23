param(
    [Parameter(Mandatory = $true)]
    [string]$InputSvg,

    [Parameter(Mandatory = $true)]
    [string]$OutputDrawio
)

$ErrorActionPreference = 'Stop'

function ConvertTo-PlainLabel {
    param([AllowEmptyString()][string]$Value)

    if ([string]::IsNullOrEmpty($Value)) {
        return ''
    }

    # Remove invisible editor artefacts before turning the remaining HTML into text.
    $text = [regex]::Replace(
        $Value,
        '<span[^>]*(?:rgba\(0,\s*0,\s*0,\s*0\)|font-size:\s*1px)[^>]*>.*?</span>',
        '',
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase -bor
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
    $text = [regex]::Replace($text, '<br\s*/?>', "`n", 'IgnoreCase')
    $text = [regex]::Replace($text, '</(?:div|p|pre|li|tr)>', "`n", 'IgnoreCase')
    $text = [regex]::Replace($text, '<[^>]+>', '')
    $text = [System.Net.WebUtility]::HtmlDecode($text)
    $text = $text.Replace([char]0x00A0, ' ')
    $text = $text.Replace("`r`n", "`n").Replace("`r", "`n")
    $text = [regex]::Replace($text, "`n{3,}", "`n`n")
    return $text.TrimEnd()
}

function New-GeometryElement {
    param(
        [System.Xml.XmlDocument]$Document,
        [double]$X,
        [double]$Y,
        [double]$Width,
        [double]$Height,
        [bool]$IncludeAlternateBounds = $false
    )

    $geometry = $Document.CreateElement('mxGeometry')
    if ($X -ne 0) { $geometry.SetAttribute('x', [string]$X) }
    if ($Y -ne 0) { $geometry.SetAttribute('y', [string]$Y) }
    $geometry.SetAttribute('width', [string]$Width)
    $geometry.SetAttribute('height', [string]$Height)
    $geometry.SetAttribute('as', 'geometry')

    if ($IncludeAlternateBounds) {
        $bounds = $Document.CreateElement('mxRectangle')
        $bounds.SetAttribute('width', [string]$Width)
        $bounds.SetAttribute('height', [string]$Height)
        $bounds.SetAttribute('as', 'alternateBounds')
        [void]$geometry.AppendChild($bounds)
    }

    return $geometry
}

function New-CellElement {
    param(
        [System.Xml.XmlDocument]$Document,
        [string]$Id,
        [string]$Parent,
        [AllowEmptyString()][string]$Value,
        [string]$Style,
        [double]$X,
        [double]$Y,
        [double]$Width,
        [double]$Height,
        [bool]$IncludeAlternateBounds = $false
    )

    $cell = $Document.CreateElement('mxCell')
    $cell.SetAttribute('id', $Id)
    $cell.SetAttribute('parent', $Parent)
    $cell.SetAttribute('value', $Value)
    $cell.SetAttribute('style', $Style)
    $cell.SetAttribute('vertex', '1')
    [void]$cell.AppendChild((New-GeometryElement -Document $Document -X $X -Y $Y -Width $Width -Height $Height -IncludeAlternateBounds $IncludeAlternateBounds))
    return $cell
}

$svgDocument = [System.Xml.XmlDocument]::new()
$svgDocument.PreserveWhitespace = $true
$svgDocument.Load($InputSvg)
$embeddedXml = $svgDocument.DocumentElement.GetAttribute('content')
if ([string]::IsNullOrWhiteSpace($embeddedXml)) {
    throw 'The SVG does not contain an editable draw.io model in its content attribute.'
}

$drawioDocument = [System.Xml.XmlDocument]::new()
$drawioDocument.PreserveWhitespace = $true
$drawioDocument.LoadXml($embeddedXml)

$root = $drawioDocument.SelectSingleNode('/mxfile/diagram/mxGraphModel/root')
if ($null -eq $root) {
    throw 'The embedded draw.io document has no mxGraphModel/root element.'
}

$allCells = @($root.SelectNodes('mxCell'))
$tables = @($allCells | Where-Object { $_.GetAttribute('style').StartsWith('swimlane;') })
if ($tables.Count -eq 0) {
    throw 'No swimlane-based entity tables were found.'
}

$tableStyle = 'shape=table;html=1;startSize=0;container=1;collapsible=0;childLayout=tableLayout;fixedRows=1;rowLines=0;resizeLast=1;rounded=0;shadow=0;fillColor=#FFFFFF;strokeColor=#D6B656;strokeWidth=1;'
$headerRowStyle = 'shape=tableRow;html=1;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;fillColor=#FFF2CC;strokeColor=#D6B656;collapsible=0;dropTarget=0;points=[];portConstraint=eastwest;top=0;left=0;right=0;bottom=1;'
$bodyRowStyle = 'shape=tableRow;html=1;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;fillColor=#FFFFFF;strokeColor=#D6B656;collapsible=0;dropTarget=0;points=[];portConstraint=eastwest;top=0;left=0;right=0;bottom=1;'
$headerCellStyle = 'shape=partialRectangle;connectable=0;html=1;fillColor=none;top=0;left=0;bottom=0;right=0;overflow=hidden;whiteSpace=wrap;align=center;verticalAlign=middle;fontFamily=Helvetica;fontSize=17;fontStyle=1;fontColor=#000000;spacing=0;'
$keyCellBaseStyle = 'shape=partialRectangle;connectable=0;html=1;fillColor=none;top=0;left=0;bottom=0;right=1;overflow=hidden;whiteSpace=wrap;align=center;fontFamily=Helvetica;fontSize=14;fontStyle=1;fontColor=#000000;spacing=0;'
$valueCellBaseStyle = 'shape=partialRectangle;connectable=0;html=1;fillColor=none;top=0;left=0;bottom=0;right=0;overflow=hidden;whiteSpace=wrap;align=left;fontFamily=Consolas;fontSize=17;fontColor=#000000;spacingLeft=7;spacingRight=4;'

$convertedRows = 0
$keyedRows = 0

foreach ($table in $tables) {
    $tableId = $table.GetAttribute('id')
    $title = (ConvertTo-PlainLabel $table.GetAttribute('value')).Trim()
    $geometry = $table.SelectSingleNode('mxGeometry')
    $tableWidth = [double]$geometry.GetAttribute('width')
    $keyWidth = [Math]::Min(48, [Math]::Max(38, [Math]::Round($tableWidth * 0.12)))
    $headerHeight = 36

    $rows = @($root.SelectNodes("mxCell[@parent='$tableId' and @vertex='1']") | Sort-Object {
        [double]$_.SelectSingleNode('mxGeometry').GetAttribute('y')
    })
    if ($rows.Count -eq 0) { continue }

    $table.SetAttribute('style', $tableStyle)
    $table.SetAttribute('value', '')

    $headerRowId = "$tableId`__header_row"
    $headerCellId = "$tableId`__header_cell"
    $headerRow = New-CellElement -Document $drawioDocument -Id $headerRowId -Parent $tableId -Value '' -Style $headerRowStyle -X 0 -Y 0 -Width $tableWidth -Height $headerHeight
    $headerCell = New-CellElement -Document $drawioDocument -Id $headerCellId -Parent $headerRowId -Value $title -Style $headerCellStyle -X 0 -Y 0 -Width $tableWidth -Height $headerHeight -IncludeAlternateBounds $true
    [void]$root.InsertBefore($headerRow, $rows[0])
    [void]$root.InsertBefore($headerCell, $rows[0])

    foreach ($row in $rows) {
        $rowId = $row.GetAttribute('id')
        $plainText = ConvertTo-PlainLabel $row.GetAttribute('value')
        $key = ''
        $bodyText = $plainText
        $match = [regex]::Match(
            $plainText,
            '^\s*((?:PK|FK|UQ|CK|IX)(?:\s*,\s*(?:PK|FK|UQ|CK|IX))*)(?:\s+|$)',
            'IgnoreCase'
        )
        if ($match.Success) {
            $key = ([regex]::Replace($match.Groups[1].Value, '\s*,\s*', ', ')).ToUpperInvariant()
            $bodyText = $plainText.Substring($match.Length).TrimStart()
            $keyedRows++
        } else {
            $bodyText = $plainText.TrimStart()
        }

        $rowGeometry = $row.SelectSingleNode('mxGeometry')
        $rowY = [double]$rowGeometry.GetAttribute('y')
        $rowHeight = [double]$rowGeometry.GetAttribute('height')
        $row.SetAttribute('value', '')
        $row.SetAttribute('style', $bodyRowStyle)
        $rowGeometry.SetAttribute('width', [string]$tableWidth)
        $rowGeometry.SetAttribute('height', [string]$rowHeight)

        $verticalStyle = if ($rowHeight -gt 32) { 'verticalAlign=top;spacingTop=5;' } else { 'verticalAlign=middle;' }
        $keyStyle = $keyCellBaseStyle + $verticalStyle
        $valueStyle = $valueCellBaseStyle + $verticalStyle
        $encodedBody = [System.Net.WebUtility]::HtmlEncode($bodyText).Replace("`n", '<br>')
        $bodyHtml = "<div style=`"white-space:pre-wrap;line-height:1.2;`">$encodedBody</div>"

        $keyCell = New-CellElement -Document $drawioDocument -Id "$rowId`__key" -Parent $rowId -Value $key -Style $keyStyle -X 0 -Y 0 -Width $keyWidth -Height $rowHeight -IncludeAlternateBounds $true
        $valueCell = New-CellElement -Document $drawioDocument -Id "$rowId`__value" -Parent $rowId -Value $bodyHtml -Style $valueStyle -X $keyWidth -Y 0 -Width ($tableWidth - $keyWidth) -Height $rowHeight -IncludeAlternateBounds $true

        [void]$root.InsertAfter($valueCell, $row)
        [void]$root.InsertAfter($keyCell, $row)
        $convertedRows++
    }
}

$settings = [System.Xml.XmlWriterSettings]::new()
$settings.Encoding = [System.Text.UTF8Encoding]::new($false)
$settings.Indent = $true
$settings.IndentChars = '  '
$settings.NewLineChars = "`r`n"
$settings.NewLineHandling = [System.Xml.NewLineHandling]::Replace

$writer = [System.Xml.XmlWriter]::Create($OutputDrawio, $settings)
try {
    $drawioDocument.Save($writer)
} finally {
    $writer.Dispose()
}

[pscustomobject]@{
    Output = $OutputDrawio
    Tables = $tables.Count
    Rows = $convertedRows
    KeyedRows = $keyedRows
    Bytes = (Get-Item -LiteralPath $OutputDrawio).Length
}
