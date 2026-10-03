package org.maventwin.observer;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.apache.maven.AbstractMavenLifecycleParticipant;
import org.apache.maven.execution.MavenSession;
import org.apache.maven.project.MavenProject;
import org.apache.maven.model.io.xpp3.MavenXpp3Writer;
import org.apache.maven.lifecycle.MavenExecutionPlan;
import org.apache.maven.lifecycle.internal.LifecycleTask;
import org.apache.maven.lifecycle.internal.LifecycleExecutionPlanCalculator;
import org.apache.maven.plugin.MojoExecution;
/** Observes runtime in-memory models and asks Maven's actual plan calculator for a non-executed plan. */
public class Observer extends AbstractMavenLifecycleParticipant {
  public LifecycleExecutionPlanCalculator calculator;
  private String cell(Object x) {return x==null?"":x.toString().replace("\t"," ").replace("\r"," ").replace("\n"," ");}
  @Override public void afterSessionEnd(MavenSession session) {
    String target=System.getProperty("maventwin.observer.output");if(target==null || session.getProjects()==null)return;
    try {
      Path dir=Paths.get(target);Files.createDirectories(dir);int i=0;
      for(MavenProject project:session.getProjects()) {
        try(Writer w=Files.newBufferedWriter(dir.resolve(String.format("%03d-final-model.xml",i++)),StandardCharsets.UTF_8)) {
          new MavenXpp3Writer().write(w,project.getModel());
        }
      }
    } catch(Exception e){System.err.println("MAVENTWIN_FINAL_MODEL_FAILURE: "+e);}
  }
  @Override public void afterProjectsRead(MavenSession session) {
    String target=System.getProperty("maventwin.observer.output");
    if(target==null)return;
    try {
      Path dir=Paths.get(target);Files.createDirectories(dir);
      int i=0;
      for(MavenProject project:session.getProjects()) {
        String stem=String.format("%03d",i++);
        try(Writer w=Files.newBufferedWriter(dir.resolve(stem+"-model.xml"),StandardCharsets.UTF_8)) {
          new MavenXpp3Writer().write(w,project.getModel());
        }
        List<Object> tasks=new ArrayList<>();tasks.add(new LifecycleTask(System.getProperty("maventwin.observer.phase","package")));
        try {
          LifecycleExecutionPlanCalculator selected=calculator;
          if(selected==null && session.getContainer()!=null)selected=session.getContainer().lookup(LifecycleExecutionPlanCalculator.class);
          if(selected==null)throw new IllegalStateException("LifecycleExecutionPlanCalculator injection unavailable");
          MavenExecutionPlan plan=selected.calculateExecutionPlan(session,project,tasks,false);
          try(BufferedWriter w=Files.newBufferedWriter(dir.resolve(stem+"-plan.tsv"),StandardCharsets.UTF_8)) {
            w.write("order\tgroupId\tartifactId\tversion\texecutionId\tgoal\tphase\tsource\tconfiguration\n");
            int n=0;
            for(MojoExecution m:plan.getMojoExecutions()) {
              w.write((n++)+"\t"+cell(m.getGroupId())+"\t"+cell(m.getArtifactId())+"\t"+cell(m.getVersion())+"\t"+cell(m.getExecutionId())+"\t"+cell(m.getGoal())+"\t"+cell(m.getLifecyclePhase())+"\t"+cell(m.getSource())+"\t"+cell(m.getConfiguration())+"\n");
            }
          }
          Files.writeString(dir.resolve(stem+"-plan-status.txt"),"CALCULATED_NOT_EXECUTED\n",StandardCharsets.UTF_8);
        } catch(Exception e) {
          try(PrintWriter w=new PrintWriter(Files.newBufferedWriter(dir.resolve(stem+"-plan-error.txt"),StandardCharsets.UTF_8))) {e.printStackTrace(w);}
        }
      }
      Files.writeString(dir.resolve("observer-status.txt"),"MODELS_CAPTURED="+i+"\n",StandardCharsets.UTF_8);
    } catch(Exception e) {System.err.println("MAVENTWIN_OBSERVER_FAILURE: "+e);}
  }
}
