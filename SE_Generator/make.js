useLibrary('threads');
importClass(java.io.File);
importClass(arkham.project.ProjectUtilities);
importClass(arkham.sheet.RenderTarget);
importClass(ca.cgjennings.apps.arkham.project.Project);
importClass(ca.cgjennings.seplugins.csv.CsvFactory);
importClass(ca.cgjennings.imageio.SimpleImageWriter);

const PROJECT_FOLDER = 'SE_Generator';
const TEMPLATE_FOLDER = 'template';
const DATA_FOLDER = 'data';
const BUILD_FOLDER = 'build';
const IMAGE_FOLDER = 'images';

let headless = Eons.getScriptRunner() !== null;
let project = headless ? Project.open(new File(PROJECT_FOLDER)) : Eons.getOpenProject();

let types = [];
let dataFolder = new File(project.getFile(), DATA_FOLDER);
let dataFiles = dataFolder.listFiles();
for (let i = 0; i < dataFiles.length; i++) {
    let dataFilename = dataFiles[i].getName();
    if (dataFilename.endsWith('.csv')) {
        let type = dataFilename.replace('.csv', '');
        types.push(type);
    }
}

function process(progress) {
    function syncProject() {
        if (!headless) {
            project.synchronizeAll();
        }
    }

    function reportStatus(progress, status) {
        if (headless) {
            println(status);
        } else {
            progress.status = status;
        }
    }

    let buildFolder = new File(project.getFile(), BUILD_FOLDER);
    ProjectUtilities.deleteAll(buildFolder);
    buildFolder.mkdirs();
    syncProject();

    let factory = new CsvFactory();
    factory.setDelimiter(',');
    factory.setQuote('"');
    factory.setExtraSpaceIgnored(false);
    factory.setIgnoreUnknownKeys(true);
    factory.setTemplateClearedForEachRow(true);
    factory.setOutputFolder(buildFolder);

    for (let i = 0; !progress.cancelled && i < types.length; i++) {
        let templateFile = new File(project.getFile(), TEMPLATE_FOLDER + '/' + types[i] + '.eon');
        let template = ResourceKit.getGameComponentFromFile(templateFile, true);
        let csvFile = new File(project.getFile(), DATA_FOLDER + '/' + types[i] + '.csv');
        reportStatus(progress, 'Processing ' + csvFile.getName() + '...');
        let csv = ProjectUtilities.getFileText(csvFile, 'utf-8');
        factory.process(template, csv);
        syncProject();
    }

    let cardFiles = buildFolder.listFiles();
    let imageFolder = new File(project.getFile(), BUILD_FOLDER + '/' + IMAGE_FOLDER);
    if (!progress.cancelled) {
        imageFolder.mkdirs();
        syncProject();
    }

    for (let i = 0; !progress.cancelled && i < cardFiles.length; i++) {
        let cardFile = cardFiles[i];
        let card = ResourceKit.getGameComponentFromFile(cardFile, true);
        let cardFilename = cardFile.getName();
        let fields = cardFilename.replace('.eon', '').split('-');
        let index = parseInt(fields[fields.length - 1]);
        let ppi = 300;
        let synthesizeBleedMargin = false;
        let imageWriter = new SimpleImageWriter('png');
        let imageFile = new File(imageFolder, cardFilename.replace('.eon', '.png'));
        reportStatus(progress, 'Generating ' + imageFile.getName() + '...');
        let sheets = card.createDefaultSheets();
        let sheet = sheets[index];
        let image = sheet.paint(RenderTarget.EXPORT, ppi, synthesizeBleedMargin);
        imageWriter.write(image, imageFile);
        syncProject();
    }
}

if (headless) {
    process({cancelled: false});
    project.close();
} else {
    Thread.busyWindow(process, 'Building...', true);
}

